const FIELD_CAP = 1024;
const TITLE_CAP = 256;

export async function postDiscord(webhookUrl, embed) {
  const res = await fetch(webhookUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ embeds: [embed] }),
  });
  return res.ok;
}

export function buildEmbed({ modName, title, issueUrl, fields, saveUrl }) {
  const embedFields = fields
    .filter((f) => f.value)
    .map((f) => ({ name: f.name, value: truncate(f.value, FIELD_CAP), inline: false }));
  embedFields.push({ name: "Save", value: saveUrl, inline: false });
  return {
    title: truncate(`[${modName}] ${title}`, TITLE_CAP),
    url: issueUrl,
    color: 0xcc3333,
    fields: embedFields.slice(0, 25),
  };
}

function truncate(text, max) {
  const str = String(text);
  return str.length > max ? str.slice(0, max - 3) + "..." : str;
}
