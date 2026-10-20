# Market allowlist: Wikipedia and sector sources admitted

Date: 2026-10-19 (Australia/Sydney). The maintainer approved this change after
the [development probe](results-2026-10-19-market-retrieval-development-probe.md)
recorded where operator evidence is lost. It is a retrieval policy change. It
reports no TRL. A separately registered held-out v2 protocol measures the
final retrieval configuration.

## Change

- **Wikipedia.** It was blocked alongside social networks from the first pipeline, with no recorded failure. It is now admitted as source type `other` at **low** credibility, with a reason telling the reader to verify claims against the primary sources it cites. At most **one** entry is admitted per market collection; further entries are deferred.
- **Sector bodies and independent analysts**, added to the existing curated lists. Each was rejected as unapproved on the 2026-10-18 held-out runs or in the probe while naming the operators those topics' anchors rely on:

| Added host | Classed as |
|---|---|
| World Nuclear Association, Fusion Industry Association, DNA Data Storage Alliance, Clean Air Task Force, Offshore Renewable Energy Catapult | `research_institute` (nonprofit / sector body) |
| IEEFA, World Nuclear Industry Status Report | `research_institute` (think tank) |
| Carbon Herald, Becker's (two titles), MD+DI | `reputable_news` (trade press) |

Social networks, video sites and the SEO market-research hosts that dominate
the rejections stay blocked or unapproved.

## Precision check

The same cached search results were run under the old and the new allowlist
(market domain, production queries, ten development topics, no new search).
Only the filtering differs. Four topics changed, each by one source:

| Topic | Admitted | Displaced | Reading |
|---|---|---|---|
| Floating offshore wind | Wikipedia "Floating offshore wind": Hywind Scotland commissioned 2017 | A university feature article | The anchor's deployments, otherwise absent |
| Direct air capture | Carbon Herald "Top 20 Direct Air Capture Companies": named firms and funding | A market-size page | Named commercial actors |
| Fusion power | Fusion Industry Association 2026 industry report | A wire item on one fusion company | Relevant and authoritative; it displaced real company news |
| DNA data storage | DNA Data Storage Alliance member list | A market-size page | Relevant but weak: membership is not deployment |

None of the four was off-topic or low quality. On these cached results, the
sources naming an anchor entity rose from 30 to 32.

## Limits

- The sector hosts came from the development topics, so they help only those sectors. A new topic in another sector benefits only from the Wikipedia change.
- The check used one cached run per topic, and the World Nuclear Association and IEEFA results appeared only under probe variants that production does not use. Their effect on production retrieval is therefore not shown here.
- A low-credibility tertiary source can still repeat an error. The credibility reason and the one-entry cap bound it; neither removes that risk.
