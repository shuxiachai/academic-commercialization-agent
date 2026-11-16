/* Names that say what kind of model they are, when that kind cannot write
 * an assessment. The form took any plain name; an account on the live site
 * had saved "qwen-vl-ocr-2025-11-20", and its run failed two minutes and
 * some 44,000 tokens in with a sentence about evidence quality and "please
 * retry". Nothing had said the name was an OCR model's.
 *
 * Read from the name alone, so it is advice and never a refusal: the note
 * says "looks like", and the name can still be saved. Each rule matches a
 * whole word of the name where a fragment would also sit inside ordinary
 * names ("mt", "image", "guard"). No model this page offers or has measured
 * matches any rule; tests/js/byok_fields_contract.mjs holds that.
 *
 * Two readers: the key form (byok_fields.js), while a name is typed or shown,
 * and the run page (app.js), for a run that failed on such a model. No
 * imports here, so either can load it. */
export const MODEL_KINDS = [
  ["ocr", /(^|[^a-z])ocr|ocr($|[^a-z])/],
  // A reranker is often named after the embedding family it belongs to (bge-reranker): asked first.
  ["rerank", /rerank/],
  ["embedding", /embed|(^|[^a-z])bge($|[^a-z])/],
  ["speech", /(^|[^a-z])(tts|asr|stt)($|[^a-z])|whisper|speech|audio|realtime|paraformer|sensevoice|cosyvoice/],
  ["image", /(^|[^a-z])image($|[^a-z])|dall-e|wanx|flux|stable-diffusion|imagen|t2i/],
  ["video", /(^|[^a-z])(video|sora|veo|t2v|i2v)($|[^a-z])|(^|[^a-z])wan[0-9]/],
  ["translation", /(^|[^a-z])mt($|[^a-z])/],
  ["moderation", /moderation|(^|[^a-z])guard($|[^a-z])/],
];

/** The kind a model's name says it is, when that kind cannot write an assessment; otherwise null. */
export function modelKind(name) {
  const plain = String(name ?? "").trim().toLowerCase();
  if (!plain) return null;
  return MODEL_KINDS.find(([, pattern]) => pattern.test(plain))?.[0] ?? null;
}
