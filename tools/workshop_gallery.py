import ctypes
import os
import time


ROOT_DIRECTORY = os.path.dirname(os.path.abspath(__file__))
GALLERY_DIRECTORY = os.path.join(
    os.path.dirname(ROOT_DIRECTORY),
    "assets",
    "workshop",
    "gallery",
)
MAX_GALLERY_IMAGE_BYTES = 1_000_000
QUERY_TIMEOUT_SECONDS = 30
QUERY_POLL_INTERVAL_SECONDS = 0.1
IMAGE_PREVIEW_TYPE = 0
STEAM_UGC_QUERY_COMPLETED_CALLBACK = 3401


def collect_gallery_images(gallery_directory):
    try:
        with os.scandir(gallery_directory) as entries:
            gallery_entries = list(entries)
    except FileNotFoundError as error:
        raise ValueError(
            f"Gallery synchronization requested, but the directory does not exist: {gallery_directory}"
        ) from error

    if not gallery_entries:
        raise ValueError(
            f"Gallery synchronization requested, but no images were found in {gallery_directory}"
        )

    image_paths = []
    for entry in gallery_entries:
        if not entry.is_file(follow_symlinks=False) or not entry.name.lower().endswith(
            (".jpg", ".jpeg", ".png")
        ):
            raise ValueError(
                f"Unsupported gallery entry: {entry.path} (expected JPG, JPEG, or PNG files)"
            )

        image_size = entry.stat(follow_symlinks=False).st_size
        if image_size <= 0 or image_size >= MAX_GALLERY_IMAGE_BYTES:
            raise ValueError(
                f"Gallery image must be non-empty and smaller than {MAX_GALLERY_IMAGE_BYTES} bytes: {entry.path}"
            )
        image_paths.append(entry.path)

    return sorted(image_paths)


class _SteamUGCQueryCompleted(ctypes.Structure):
    _fields_ = [
        ("handle", ctypes.c_uint64),
        ("result", ctypes.c_int32),
        ("num_results_returned", ctypes.c_uint32),
        ("total_matching_results", ctypes.c_uint32),
        ("cached_data", ctypes.c_bool),
    ]


_RunCallback = ctypes.CFUNCTYPE(None, ctypes.c_void_p, ctypes.c_void_p)
_RunCallResult = ctypes.CFUNCTYPE(
    None, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool, ctypes.c_uint64
)
_GetCallbackSize = ctypes.CFUNCTYPE(ctypes.c_int32, ctypes.c_void_p)


# Steamworks dispatches C++ callbacks through this vtable-compatible layout.
class _SteamCallbackVTable(ctypes.Structure):
    _fields_ = [
        ("run", _RunCallback),
        ("run_call_result", _RunCallResult),
        ("get_callback_size", _GetCallbackSize),
    ]


class _SteamCallbackBase(ctypes.Structure):
    _fields_ = [
        ("vtable", ctypes.POINTER(_SteamCallbackVTable)),
        ("callback_flags", ctypes.c_uint8),
        ("callback_id", ctypes.c_int32),
    ]


class _QueryCompletionCallback:
    def __init__(self):
        self.done = False
        self.io_failure = False
        self.result = None
        self._run = _RunCallback(self._run_callback)
        self._run_call_result = _RunCallResult(self._run_call_result_callback)
        self._get_callback_size = _GetCallbackSize(self._get_callback_size_bytes)
        self._vtable = _SteamCallbackVTable(
            self._run,
            self._run_call_result,
            self._get_callback_size,
        )
        self.base = _SteamCallbackBase(
            ctypes.pointer(self._vtable),
            0,
            STEAM_UGC_QUERY_COMPLETED_CALLBACK,
        )

    def _receive_result(self, result_pointer, io_failure):
        self.io_failure = io_failure
        if result_pointer:
            self.result = ctypes.cast(
                result_pointer,
                ctypes.POINTER(_SteamUGCQueryCompleted),
            ).contents
        self.done = True

    def _run_callback(self, _callback, result_pointer):
        self._receive_result(result_pointer, False)

    def _run_call_result_callback(
        self,
        _callback,
        result_pointer,
        io_failure,
        _api_call,
    ):
        self._receive_result(result_pointer, io_failure)

    @staticmethod
    def _get_callback_size_bytes(_callback):
        return ctypes.sizeof(_SteamUGCQueryCompleted)


class SteamUGCGalleryApi:
    def __init__(self, steam, api_library_path):
        self.steam = steam
        try:
            self._library = ctypes.CDLL(api_library_path)
        except OSError as error:
            raise RuntimeError(
                f"Unable to load Steam API library for gallery synchronization: {api_library_path}"
            ) from error

        self._interface_factory = self._bind(
            "SteamAPI_SteamUGC_v016",
            ctypes.c_void_p,
            [],
        )
        self._register_call_result = self._bind(
            "SteamAPI_RegisterCallResult",
            None,
            [ctypes.c_void_p, ctypes.c_uint64],
        )
        self._unregister_call_result = self._bind(
            "SteamAPI_UnregisterCallResult",
            None,
            [ctypes.c_void_p, ctypes.c_uint64],
        )
        self._create_details_request = self._bind(
            "SteamAPI_ISteamUGC_CreateQueryUGCDetailsRequest",
            ctypes.c_uint64,
            [
                ctypes.c_void_p,
                ctypes.POINTER(ctypes.c_uint64),
                ctypes.c_uint32,
            ],
        )
        self._set_return_additional_previews = self._bind(
            "SteamAPI_ISteamUGC_SetReturnAdditionalPreviews",
            ctypes.c_bool,
            [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_bool],
        )
        self._send_query_request = self._bind(
            "SteamAPI_ISteamUGC_SendQueryUGCRequest",
            ctypes.c_uint64,
            [ctypes.c_void_p, ctypes.c_uint64],
        )
        self._get_num_additional_previews = self._bind(
            "SteamAPI_ISteamUGC_GetQueryUGCNumAdditionalPreviews",
            ctypes.c_uint32,
            [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32],
        )
        self._get_additional_preview = self._bind(
            "SteamAPI_ISteamUGC_GetQueryUGCAdditionalPreview",
            ctypes.c_bool,
            [
                ctypes.c_void_p,
                ctypes.c_uint64,
                ctypes.c_uint32,
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_char),
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_char),
                ctypes.c_uint32,
                ctypes.POINTER(ctypes.c_int32),
            ],
        )
        self._release_query = self._bind(
            "SteamAPI_ISteamUGC_ReleaseQueryUGCRequest",
            ctypes.c_bool,
            [ctypes.c_void_p, ctypes.c_uint64],
        )
        self._remove_item_preview = self._bind(
            "SteamAPI_ISteamUGC_RemoveItemPreview",
            ctypes.c_bool,
            [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32],
        )
        self._add_item_preview_file = self._bind(
            "SteamAPI_ISteamUGC_AddItemPreviewFile",
            ctypes.c_bool,
            [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_char_p, ctypes.c_int32],
        )

        self._interface = self._interface_factory()
        if not self._interface:
            raise RuntimeError("Steam API did not provide the ISteamUGC interface")

    def _bind(self, function_name, result_type, argument_types):
        try:
            function = getattr(self._library, function_name)
        except AttributeError as error:
            raise RuntimeError(
                f"Steam API library does not export {function_name}; update the CMT Steamworks dependency"
            ) from error
        function.restype = result_type
        function.argtypes = argument_types
        return function

    def get_additional_preview_types(self, workshop_item_id):
        item_ids = (ctypes.c_uint64 * 1)(workshop_item_id)
        query_handle = self._create_details_request(
            self._interface,
            item_ids,
            1,
        )
        if not query_handle:
            raise RuntimeError("Steam could not create a Workshop preview query")

        try:
            if not self._set_return_additional_previews(
                self._interface,
                query_handle,
                True,
            ):
                raise RuntimeError("Steam could not include additional previews in the query")

            api_call = self._send_query_request(self._interface, query_handle)
            if not api_call:
                raise RuntimeError("Steam could not send the Workshop preview query")

            callback = _QueryCompletionCallback()
            self._register_call_result(ctypes.byref(callback.base), api_call)
            try:
                deadline = time.monotonic() + QUERY_TIMEOUT_SECONDS
                while not callback.done:
                    self.steam.run_callbacks()
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Timed out while querying Workshop previews")
                    time.sleep(QUERY_POLL_INTERVAL_SECONDS)
            finally:
                self._unregister_call_result(ctypes.byref(callback.base), api_call)

            if callback.io_failure or callback.result is None:
                raise RuntimeError("Steam failed while querying Workshop previews")
            if callback.result.handle != query_handle:
                raise RuntimeError("Steam returned a different Workshop preview query")
            if callback.result.result != 1:
                raise RuntimeError(
                    f"Steam preview query failed with result {callback.result.result}"
                )
            if callback.result.num_results_returned != 1:
                raise RuntimeError(
                    f"Steam returned no details for Workshop item {workshop_item_id}"
                )

            preview_count = self._get_num_additional_previews(
                self._interface,
                query_handle,
                0,
            )
            preview_types = []
            for preview_index in range(preview_count):
                url_or_video_id = ctypes.create_string_buffer(1024)
                original_filename = ctypes.create_string_buffer(260)
                preview_type = ctypes.c_int32()
                if not self._get_additional_preview(
                    self._interface,
                    query_handle,
                    0,
                    preview_index,
                    url_or_video_id,
                    len(url_or_video_id),
                    original_filename,
                    len(original_filename),
                    ctypes.byref(preview_type),
                ):
                    raise RuntimeError(
                        f"Steam could not read Workshop preview {preview_index}"
                    )
                preview_types.append(preview_type.value)
            return preview_types
        finally:
            self._release_query(self._interface, query_handle)

    def remove_item_preview(self, update_handle, preview_index):
        return self._remove_item_preview(
            self._interface,
            update_handle,
            preview_index,
        )

    def add_item_preview_file(self, update_handle, image_path):
        return self._add_item_preview_file(
            self._interface,
            update_handle,
            os.fsencode(image_path),
            IMAGE_PREVIEW_TYPE,
        )


def replace_gallery_previews(api, update_handle, workshop_item_id, image_paths):
    if not image_paths:
        raise ValueError("Gallery synchronization requires at least one image")

    preview_types = api.get_additional_preview_types(workshop_item_id)
    image_indexes = [
        index
        for index, preview_type in enumerate(preview_types)
        if preview_type == IMAGE_PREVIEW_TYPE
    ]
    for preview_index in reversed(image_indexes):
        if not api.remove_item_preview(update_handle, preview_index):
            raise RuntimeError(
                f"Steam could not remove existing gallery image preview {preview_index}"
            )

    for image_path in image_paths:
        if not api.add_item_preview_file(update_handle, image_path):
            raise RuntimeError(f"Steam could not add gallery image: {image_path}")
