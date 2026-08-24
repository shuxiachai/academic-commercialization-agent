/* Topic-shape checks used before a paid run starts. */

const EAST_ASIAN_SCRIPT_RE = /[\p{Script=Han}\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Hangul}]/u;

// These patterns intentionally recognise requests, not subject domains. A
// topic about poetry-generation technology is valid research; an imperative
// asking this assessment service to write a poem is almost certainly a wrong
// task. Keeping the anchor and output nouns narrow favours precision over
// catching every possible non-research request.
const ENGLISH_CONTENT_REQUEST_RE = /^(?:please\s+)?(?:write|tell|make|create|compose)\s+(?:me\s+)?(?=.{0,64}\b(?:poem|joke|story|recipe|song|email|essay)\b)/iu;
const EAST_ASIAN_CONTENT_REQUEST_RE = /^(?:请|帮我|给我)(?=.{0,24}(?:写|讲|编|创作|生成))(?=.{0,24}(?:诗|笑话|故事|菜谱|食谱|歌曲|邮件|作文))/u;

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
  const topic = String(value ?? "").trim();
  if (
    ENGLISH_CONTENT_REQUEST_RE.test(topic)
    || EAST_ASIAN_CONTENT_REQUEST_RE.test(topic)
  ) return true;

  // A paper supplies scope for a short title, but it cannot turn an explicit
  // content-generation command into a commercialization research question.
  if (hasPaper) return false;
  if (EAST_ASIAN_SCRIPT_RE.test(topic)) {
    const compact = topic.replace(/[\p{P}\p{S}\s]/gu, "");
    return compact.length < 8;
  }

  const tokens = topic.match(/[\p{L}\p{N}]+/gu) ?? [];
  return tokens.length < 3;
}
