import ctypes
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(
    0,
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"),
)

from workshop_gallery import (
    IMAGE_PREVIEW_TYPE,
    STEAM_UGC_QUERY_COMPLETED_CALLBACK,
    SteamUGCGalleryApi,
    _SteamCallbackBase,
    _SteamUGCQueryCompleted,
    collect_gallery_images,
    replace_gallery_previews,
)


class WorkshopGalleryTests(unittest.TestCase):
    def test_collects_supported_images_in_alphabetical_order(self):
        with tempfile.TemporaryDirectory() as gallery_directory:
            for name in ("02-economy.jpg", "01-overview.PNG"):
                with open(os.path.join(gallery_directory, name), "wb") as image:
                    image.write(b"image")

            self.assertEqual(
                collect_gallery_images(gallery_directory),
                [
                    os.path.join(gallery_directory, "01-overview.PNG"),
                    os.path.join(gallery_directory, "02-economy.jpg"),
                ],
            )

    def test_rejects_missing_or_empty_gallery(self):
        with tempfile.TemporaryDirectory() as directory:
            missing_directory = os.path.join(directory, "missing")
            with self.assertRaisesRegex(ValueError, "directory does not exist"):
                collect_gallery_images(missing_directory)

            with self.assertRaisesRegex(ValueError, "no images were found"):
                collect_gallery_images(directory)

    def test_rejects_unsupported_entries_and_oversized_images(self):
        with tempfile.TemporaryDirectory() as gallery_directory:
            with open(os.path.join(gallery_directory, "preview.gif"), "wb") as image:
                image.write(b"image")
            with self.assertRaisesRegex(ValueError, "expected JPG, JPEG, or PNG"):
                collect_gallery_images(gallery_directory)

        with tempfile.TemporaryDirectory() as gallery_directory:
            image_path = os.path.join(gallery_directory, "large.png")
            with open(image_path, "wb") as image:
                image.truncate(1_000_000)
            with self.assertRaisesRegex(ValueError, "smaller than 1000000 bytes"):
                collect_gallery_images(gallery_directory)

    def test_replaces_only_image_previews_and_preserves_other_preview_types(self):
        class FakeGalleryApi:
            def __init__(self):
                self.removed_indexes = []
                self.added_paths = []

            def get_additional_preview_types(self, workshop_item_id):
                self.workshop_item_id = workshop_item_id
                return [IMAGE_PREVIEW_TYPE, 1, IMAGE_PREVIEW_TYPE, 2]

            def remove_item_preview(self, update_handle, preview_index):
                self.removed_indexes.append((update_handle, preview_index))
                return True

            def add_item_preview_file(self, update_handle, image_path):
                self.added_paths.append((update_handle, image_path))
                return True

        api = FakeGalleryApi()
        image_paths = ["01-overview.png", "02-economy.jpg"]
        replace_gallery_previews(api, 42, 1234, image_paths)

        self.assertEqual(api.workshop_item_id, 1234)
        self.assertEqual(api.removed_indexes, [(42, 2), (42, 0)])
        self.assertEqual(api.added_paths, [(42, path) for path in image_paths])

    def test_refuses_to_delete_previews_for_an_empty_gallery(self):
        class FakeGalleryApi:
            def get_additional_preview_types(self, _workshop_item_id):
                raise AssertionError("Must not query or delete previews")

        with self.assertRaisesRegex(ValueError, "at least one image"):
            replace_gallery_previews(FakeGalleryApi(), 42, 1234, [])

    def test_queries_additional_preview_types_through_steam_callback(self):
        class FakeFunction:
            def __init__(self, function):
                self.function = function

            def __call__(self, *arguments):
                return self.function(*arguments)

        class FakeSteam:
            def run_callbacks(self):
                pass

        class FakeLibrary:
            def __init__(self):
                self.released_queries = []
                self.unregistered_calls = []
                self.preview_types = [0, 1, 2]
                self.SteamAPI_SteamUGC_v016 = FakeFunction(lambda: 123)
                self.SteamAPI_RegisterCallResult = FakeFunction(
                    self.register_call_result
                )
                self.SteamAPI_UnregisterCallResult = FakeFunction(
                    self.unregister_call_result
                )
                self.SteamAPI_ISteamUGC_CreateQueryUGCDetailsRequest = FakeFunction(
                    lambda *_arguments: 456
                )
                self.SteamAPI_ISteamUGC_SetReturnAdditionalPreviews = FakeFunction(
                    lambda *_arguments: True
                )
                self.SteamAPI_ISteamUGC_SendQueryUGCRequest = FakeFunction(
                    lambda *_arguments: 789
                )
                self.SteamAPI_ISteamUGC_GetQueryUGCNumAdditionalPreviews = FakeFunction(
                    lambda *_arguments: len(self.preview_types)
                )
                self.SteamAPI_ISteamUGC_GetQueryUGCAdditionalPreview = FakeFunction(
                    self.get_additional_preview
                )
                self.SteamAPI_ISteamUGC_ReleaseQueryUGCRequest = FakeFunction(
                    self.release_query
                )
                self.SteamAPI_ISteamUGC_RemoveItemPreview = FakeFunction(
                    lambda *_arguments: True
                )
                self.SteamAPI_ISteamUGC_AddItemPreviewFile = FakeFunction(
                    lambda *_arguments: True
                )

            def register_call_result(self, callback_pointer, api_call):
                callback = ctypes.cast(
                    callback_pointer,
                    ctypes.POINTER(_SteamCallbackBase),
                ).contents
                self.callback_id = callback.callback_id
                self.callback_size = callback.vtable.contents.get_callback_size(
                    callback_pointer
                )
                result = _SteamUGCQueryCompleted(456, 1, 1, 1, False)
                self.query_result = result
                callback.vtable.contents.run_call_result(
                    callback_pointer,
                    ctypes.addressof(result),
                    False,
                    api_call,
                )

            def unregister_call_result(self, _callback_pointer, api_call):
                self.unregistered_calls.append(api_call)

            def get_additional_preview(
                self,
                _interface,
                _query_handle,
                _item_index,
                preview_index,
                _url_buffer,
                _url_buffer_size,
                _filename_buffer,
                _filename_buffer_size,
                preview_type_pointer,
            ):
                ctypes.cast(
                    preview_type_pointer,
                    ctypes.POINTER(ctypes.c_int32),
                ).contents.value = self.preview_types[preview_index]
                return True

            def release_query(self, _interface, query_handle):
                self.released_queries.append(query_handle)
                return True

        library = FakeLibrary()
        with patch("workshop_gallery.ctypes.CDLL", return_value=library):
            api = SteamUGCGalleryApi(FakeSteam(), "fake-steam-api.dll")
            self.assertEqual(api.get_additional_preview_types(1234), [0, 1, 2])

        self.assertEqual(library.callback_id, STEAM_UGC_QUERY_COMPLETED_CALLBACK)
        self.assertEqual(library.callback_size, ctypes.sizeof(_SteamUGCQueryCompleted))
        self.assertEqual(library.unregistered_calls, [789])
        self.assertEqual(library.released_queries, [456])


if __name__ == "__main__":
    unittest.main()
