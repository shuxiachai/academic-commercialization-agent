/* Topic-shape checks used before a paid run starts. */

const EAST_ASIAN_SCRIPT_RE = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;

/**
 * Return true only for topics that are very likely too broad for three-domain
 * retrieval. This is a confirmation prompt, not validation: two-word topics
 * can be legitimate, while silently spending a search quota on "AI education"
 * already produced zero validated academic sources in production.
 *
 * A paper supplies the missing scope, so its extracted topic is never warned
 * on length alone. Different thresholds are intentional because languages
 * without spaces encode a useful phrase in characters rather than tokens.
 */
export function needsScopeWarning(value, { hasPaper = false } = {}) {
  if (hasPaper) return false;

  const topic = String(value ?? "").trim();
  if (EAST_ASIAN_SCRIPT_RE.test(topic)) {
    const compact = topic.replace(/[\p{P}\p{S}\s]/gu, "");
    return compact.length < 8;
  }

  const tokens = topic.match(/[\p{L}\p{N}]+/gu) ?? [];
  return tokens.length < 3;
}
