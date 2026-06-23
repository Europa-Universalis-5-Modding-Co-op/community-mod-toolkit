// Field and save-format checks shared by /api/presign and /api/submit.

export const REQUIRED_FIELDS = [
  "title",
  "steps",
  "expected",
  "actual",
  "eu5_version",
  "mod_version",
  "other_mods",
];

const MAX_LENGTHS = {
  title: 200,
  steps: 5000,
  expected: 2000,
  actual: 2000,
  eu5_version: 60,
  mod_version: 60,
  other_mods: 4000,
  contact: 200,
  diagnostic: 500,
};

export function validateFields(fields) {
  const errors = [];
  for (const key of REQUIRED_FIELDS) {
    if (!String(fields[key] ?? "").trim()) errors.push(`missing: ${key}`);
  }
  for (const [key, max] of Object.entries(MAX_LENGTHS)) {
    if (String(fields[key] ?? "").length > max) errors.push(`too long: ${key}`);
  }
  return { ok: errors.length === 0, errors };
}

export function hasSavMagic(bytes) {
  // EU5 saves begin with ASCII "SAV".
  return bytes.length >= 3 && bytes[0] === 0x53 && bytes[1] === 0x41 && bytes[2] === 0x56;
}
