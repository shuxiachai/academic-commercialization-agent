# Academic Commercialization Assessment: perovskite-silicon tandem solar cells

<!-- decision-applicability:v1 -->

> **Assessment applicability (code-derived):** Mode `decision_support`. Actor-specific `GO/NO_GO` is permitted by context completeness; the conclusion still depends on the cited evidence. Success-criteria provenance: `not_established`. Any additional decision threshold is an analyst proposal unless explicitly identified as owner-approved; a cited benchmark does not establish owner approval.

## Executive Summary

Perovskite-silicon tandem solar cells have independently certified small-area cell efficiencies that rose from 29.15% in 2020 to 32.73% on a 1 cm² monolithic device in 2026 [A5][A3]. A 2026 study states that monolithic tandems have achieved efficiencies approaching 35%. That figure is context within the paper, not a result the paper certified [A2]. Reported operational stability has grown from hundreds of hours to the low thousands of hours under laboratory protocols, and those protocols differ across studies [A5][A1][A3]. Unresolved technical barriers include uneven phase composition (phase homogeneity) in wide-bandgap perovskite absorbers and fill-factor losses linked to a "photoshunt" mechanism [A1][A6][A2].

Commercial activity has begun among a small number of companies:

- Oxford PV announced the first utility-scale deployment of 24.5%-efficient 72-cell tandem modules in 2024 [M7][M2].
- Trina Solar reported a 29.2% (907 W), 3.1 m² tandem module verified by TÜV SÜD. It also reported a first commercial order for a premium residential project in New Zealand [M1].
- LONGi and JinkoSolar are reported to hold lab-cell records of about 34.8% [M2][M4].

Market-size estimates cover the broader perovskite solar cell market, not tandems alone. They differ by roughly 12× for 2026 [M3][M6][M8].

The patent sample has eight records. It shows filings by universities (KFUPM, UNC/ASU) and companies (Caelux, Chint, Solar-Tectic) [P1, P2, P3, P4, P5, P6, P7, P8]. Any white-space observations from this sample are preliminary analyst inferences, not freedom-to-operate conclusions [P1, P2, P3, P4, P5, P6, P7, P8].

The supplied decision is whether the Technology Transfer Office (TTO) should license a lab-scale university tandem technology for utility-scale modules. This report concludes **DEFER** for three reasons [A1][A3][M6][P1, P2, P3, P4, P5, P6, P7, P8]:

- The asset's own performance, stability, IP scope and legal status are not established in the validated evidence.
- The evidence contains no field durability data.
- The evidence contains no yield or cost data.

## 1. Technology Overview & Maturity

**Working principle.** A wide-bandgap metal-halide perovskite top cell absorbs high-energy photons. A silicon bottom cell absorbs the lower-energy part of the spectrum [A1][P3][P6]. A 2016 study states that perovskite tandem architectures could boost commercial silicon module efficiency from about 20% toward 30% [A6]. That figure is a module-level projection. It should not be compared directly with the small-area cell certifications reported later [A6][A3].

**Architectures in the evidence.**

| Architecture | Evidence | Source |
|---|---|---|
| Four-terminal (mechanically stacked) | About 1.74 eV perovskite cells (over 17% on small areas; 14.7% on 0.715 cm²) were combined with a 19%-efficient silicon cell. This showed that four-terminal tandems above 25% are feasible | [A6] |
| Monolithic two-terminal | Certified 29.15% with a 1.68 eV absorber | [A5] |
| Monolithic two-terminal | Independently certified 32.73% on 1 cm², built on silicon heterojunction (HJT) bottom cells and fabricated in ambient air | [A3] |
| Three-terminal "middle contact" | Over 30% described as "feasible". This appears to be a projected value, not a certified measurement | [P6] |
| Four-terminal module overlay | Perovskite-on-glass laminated over silicon cells | [P4][P8] |

**Efficiency trajectory (observed facts; small-area cells unless stated).**

- 2016: four-terminal tandems above 25% were shown to be feasible [A6].
- 2020: a monolithic tandem was certified at 29.15%, with tandem open-circuit voltage up to 1.92 V [A5].
- 2026: a 1 cm² monolithic tandem was independently certified at 32.73% [A3].
- 2026: "approaching 35%" is reported as context for the field, not as a result of that paper [A2].
- Industry cell records of 34.85% (LONGi) and 34.76% (JinkoSolar, perovskite/TOPCon) come from an unverified company-style source. Treat them as attributed, provisional claims [M2].
- Module scale:
  - Trina reports 29.2% on a 3.1 m² module, verified by TÜV SÜD and reported via trade news [M1].
  - Oxford PV reports 24.5% on commercial 72-cell modules [M7].
  - Oxford PV also reports 26.9% on a 60-cell residential module certified by Fraunhofer CalLab [M5].

The module figures and the cell figures measure different things at different areas. They are not interchangeable [M1][M5][M7][A3].

**Stability evidence (observed facts).** Test protocols differ across these studies, so the results are not directly comparable [A5][A1][A3][A8].

| Device / condition | Result | Source |
|---|---|---|
| Unencapsulated tandem, operating in air | 95% of initial efficiency retained after 300 h | [A5] |
| Encapsulated tandem, one-sun maximum power point (MPP), 25 °C | 93% retained after 1211 h | [A1] |
| Encapsulated tandem, one-sun MPP, 65 °C | 88% retained after 1000 h | [A1] |
| Unencapsulated tandem, continuous MPP tracking | T80 lifetime of 2182 h (time to fall to 80% of initial efficiency) | [A3] |
| Single-junction perovskite cells (not tandem), MPP, 1 sun, room temperature | 90% retained after 500 h (97% after recovery in the dark) | [A8] |

The validated academic sources report no outdoor field data, no damp-heat data and no reliability data under certification standards [A1][A3][A5].

**Key technical levers and barriers.**

- **Hole-selective self-assembled monolayers (SAMs).**
  - A methyl-substituted carbazole SAM gave an ideality factor of 1.26 and single-junction fill factors up to 84%. It also kept a 1.68 eV absorber phase-stable under illumination [A5].
  - Steric hindrance in polymeric SAMs can leave a barrier to hole extraction. A3 addressed this by electrostatically intercalating phenethylammonium iodide into the SAM [A3].
- **Wide-bandgap absorber homogeneity.**
  - Perovskites of about 1.75 eV have historically shown poor stability under light and heat [A6].
  - In 2026, uncontrolled nucleation and disordered crystallization are still described as a grave challenge. A1 addressed this through alkylphosphonic acid colloidal engineering [A1].
- **Fill factor.**
  - Fill-factor losses are identified as the main reason tandems still fall short of the thermodynamic limit [A2].
  - A photoshunt arises from competition between charge extraction and recombination. It can be hidden when the bottom cell limits the current [A2].
  - This evidence comes from a single study with one citation [A2].
- **Foundational single-junction concepts.**
  - Rubidium-containing multi-cation lattices kept efficiencies above 20% for over 500 h with a polymer coating [A7]. The A7 record combines two distinct Science papers, so attribution is somewhat uncertain [A7].
  - Contact passivation gave certified single-junction cells of 20.1% (0.049 cm²) and 19.5% (1.1 cm²) [A8].
- **Excluded source.** One low-credibility, non-peer-reviewed repository deposit claims that a quantum-computing simulation pushes tandem efficiency well beyond the Shockley-Queisser limit. The claim is uncorroborated, and this report excludes it from all conclusions [A4].

**Maturity (qualitative).**

- **Field level.** The field appears to be at the stage of laboratory-validated small-area cells with independently certified efficiencies. Industry has demonstrated full-size modules and made limited first commercial deployments. Long-term field validation has not been reported [A3][A5][M1][M7].
- **Supplied university asset.** The decision context describes the asset as lab-scale, so it is most plausibly a laboratory-scale cell or process. The evidence establishes no system-level, module-level or field validation for it [A1][A3].
- **What bankability may hinge on (analyst inference).** Commercial adoption is likely to depend more on proving large-area durability and reliability, under certification-style and field conditions, than on further efficiency records [A1][A3][M6].

## 2. Patent Landscape & White Spaces

*Legal disclaimer: The following is preliminary research based on eight search-snippet records from a secondary aggregator (Google Patents). It is not legal advice, a freedom-to-operate opinion, a patentability opinion or a validity opinion. No record's legal status, claim scope or ownership has been verified against an issuing office. Any commercial or licensing decision requires a comprehensive search and claims-level review by qualified patent counsel in each relevant jurisdiction.*

**Patent records.** Applicants are shown as listed by Google Patents, which notes that its list may be inaccurate [P1, P2, P3, P4, P5, P6, P7, P8].

| Record | Applicant (as listed) | Type | Published | Visible disclosure focus | Source |
|---|---|---|---|---|---|
| US11437537B2 | King Fahd University of Petroleum and Minerals | Granted US patent (status unverified) | 2022-09-06 | Perovskite top cell with a silicon or CIGS bottom cell; current matching; cites prior literature (Kohnen, 26%) | [P1] |
| US20250248296A1 | University of North Carolina at Chapel Hill | Published US application | 2025-07-31 | Defect engineering in 1.65 eV wide-bandgap perovskite; blade coating on fully textured silicon; applicant reports a 28.6% tandem | [P2] |
| AU2024406053A1 | Chint New Energy Technology Co Ltd | Published AU application | 2026-07-02 | Tandem and preparation method addressing humidity, oxygen and interface effects; comparative example uses a single-layer NiO hole transport layer | [P3] |
| WO2022066707A1 | Caelux Corp | WO publication | 2022-03-31 | Perovskite-on-glass laid over silicon cells; parallel or 4-terminal connection; glass-on-glass | [P4] |
| US9653696B2 | SOLAR-TECTIC LLC | US patent (status unverified) | 2017-05-16 | Tin perovskite on a thin-film silicon tandem | [P5] |
| US11756744B1 | King Fahd University of Petroleum and Minerals | US patent (status unverified) | 2023-09-12 | Three-terminal "middle contact" tandem; low-cost Cz or metallurgical-grade silicon bottom cells; modified silicon surface used as the electron transport layer | [P6] |
| WO2021030491A1 | University of North Carolina at Chapel Hill; Arizona State University (listed entities) | WO publication | 2021-02-18 | Planarizing the textured silicon bottom cell, either with the perovskite itself or with an intermediate layer | [P7] |
| WO2024097417A1 | Caelux Corp | WO publication | 2024-05-10 | Encapsulated 4-terminal modules; UV-cured index-matching layer; also covers non-silicon tandems | [P8] |

**Observations.**

- The sample mixes academic holders (KFUPM, UNC/ASU) with industrial filers (Caelux, Chint, Solar-Tectic) [P1, P2, P3, P4, P5, P6, P7, P8].
- Eight records cannot support conclusions about filing volume, concentration or how crowded the field is [P1, P2, P3, P4, P5, P6, P7, P8].
- The disclosures describe core monolithic two-terminal concepts. These include current matching and series connection through a tunnel junction or recombination layer. Whether any of this content is actually claimed is not established [P1][P6].
- Solution-processed deposition on textured silicon appears to be an active area of academic filing. This may matter for an academic asset that coats top cells onto industrial textured wafers [P2][P7].
- The module-level filings in the sample focus on 4-terminal or overlay configurations [P4][P8].
- Efficiency figures in the patent disclosures (26%, 28.6%, over 30%) are as reported by applicants. They are not independently certified, and the three-terminal figure appears to be a projection [P1][P2][P6].
- P5's age does not imply that it has lapsed or that anyone has freedom to operate. Family members, continuations and foreign equivalents may still apply [P5].

**Possibly underexplored areas (analyst inference; low confidence).** Absence from a small sample is not evidence of absence [P1, P2, P3, P4, P5, P6, P7, P8].

- **Lead-free or reduced-lead top cells on textured wafer silicon.** Only P5 addresses a tin perovskite, and it pairs it with thin-film silicon rather than wafers [P5][P2][P7].
- **Lifecycle and manufacturing support.** No snippet visibly addresses [P1, P2, P3, P4, P5, P6, P7, P8]:
  - end-of-life recycling or lead recovery;
  - in-line measurement of perovskite layers on textured silicon;
  - diagnosis of degradation in the field;
  - bifacial tandem operation.
- **Scale-up and two-terminal module interconnection.** No snippet visibly addresses conformal vapor-phase or hybrid deposition on industrial textured wafers. None visibly addresses interconnection or stringing specific to two-terminal modules [P2][P7][P4][P8].
- **SAM-based hole contacts.** None of the eight snippets visibly describes SAM-based hole-selective contacts, although these feature prominently in the academic evidence [A3][A5][P1, P2, P3, P4, P5, P6, P7, P8]. Snippets show only part of each record, so this is a prompt for targeted searching only.

None of these observations is a freedom-to-operate opportunity, a path requiring dedicated patent counsel review, or proof that an area is unprotected. Each is a preliminary analyst inference that requires professional legal review by qualified patent counsel [P1, P2, P3, P4, P5, P6, P7, P8]. The validated evidence does not include the asset's own patent filings or claims. The relevance of these filings to the specific university asset is therefore not established [P1, P2, P3, P4, P5, P6, P7, P8].

## 3. Target Industries & Use Cases

**Utility-scale PV (the supplied target application).**

- Oxford PV's first commercial 24.5% tandem modules were reported as going to a utility-scale installation. The announcement framed them around lower levelized cost of electricity (LCOE) and better land-use efficiency [M7].
- Initial volumes are described as selective [M2].
- Oxford PV claims "up to 20% more energy" than a standard silicon panel. This is a company claim relayed by trade press and has not been independently verified [M7].
- One market estimate attributes 43.0% of 2025 application value to utility-scale plants, largely from early demonstration and pilot projects [M8].
- Another market report identifies utility-scale and high-efficiency uses as the first real revenue pool [M6].
- Both are commercial estimates whose methods are not disclosed [M6][M8].

**Premium residential and distributed rooftop.**

- Trina's first commercial tandem order came from an unnamed "global high-end distributed PV customer" for a project in New Zealand [M1].
- One estimate models commercial and residential rooftops as the fastest-growing application, at 46.50% per year [M8].
- Analyst inference: where roof space is limited, buyers may value efficiency per unit area more than cost per watt [M1][M6][M7].

**Specialty products.** Oxford PV plans to allocate part of its Brandenburg output to specialty products and pilot residential applications [M7].

**Adjacent signals that are not tandem-specific.** The related-news listing includes flexible perovskite and space-application items. These concern perovskites generally, not confirmed silicon-tandem products [M1].

**Relevance to the supplied decision (analyst inference).**

- The utility-scale target matches a segment where early deployment has been observed [M7][M8].
- However, the evidence describes current utility value as mostly driven by demonstrations [M8].
- No evidence establishes utility-scale customer demand, pricing or offtake for tandem modules [M8][M6].
- Field durability evidence is absent, which may weigh especially heavily in utility procurement [A1][A3][M6].

## 4. Competitive Landscape

| Player | Region | Reported status | Evidence quality | Source |
|---|---|---|---|---|
| Oxford PV | UK / Germany | Production line in Brandenburg an der Havel; 24.5% commercial modules for utility use (2024); 26.9% 60-cell module certified by Fraunhofer CalLab (2024); seeking a high-volume site | Trade news and unverified company-style content. Production start dates conflict: 2017 per M5 versus a May 2023 announcement per M4 | [M7][M5][M4] |
| Trina Solar | China | 29.2%, 907 W, 3.1 m² module verified by TÜV SÜD; first commercial order (premium residential, New Zealand) | Trade news; order volume and value undisclosed | [M1] |
| LONGi | China | Lab cell over 33% (Nov 2023); reported 34.85% record; pilot-line roadmap in China | Market report and unverified content | [M4][M2] |
| JinkoSolar | China | Reported 34.76% perovskite/TOPCon cell (2025) | Unverified content | [M2] |
| CubicPV | US | Plans for U.S. pilot manufacturing (June 2024) | Market-report summary; low confidence | [M4] |
| Hanwha | Korea | Targets mass production of perovskite tandem cells by end-2028 | Headline only; low confidence | [M1] |
| Noak (imec / Hasselt University spin-off) | Belgium | Launched with €5 million to industrialize perovskite-silicon tandems | Headline only; low confidence | [M1] |
| UtmoLight, Microquanta | China | Profiled as scaling up perovskite modules; not confirmed as silicon-tandem developers | Characterization in a commercial report | [M6] |
| Caelux Corp, Chint | US / China | Industrial patent applicants (Caelux: module integration; Chint: hole transport layer stacks) | Patent snippets only | [P4][P8][P3] |

**Market sizing.** These figures are estimates for the broad perovskite solar cell market, not for tandems only [M3][M6][M8].

| Estimate | 2026 value | Long-range value | Annual growth rate (CAGR) | Source |
|---|---|---|---|---|
| Credence Research (via Yahoo) | USD 80.3 million | USD 1.73 billion (2035) | 40.41% (2025-2035) | [M8] |
| Precedence Research | USD 370.70 million | USD 4,182.69 million (2035) | 31.66% | [M6] |
| GlobeNewswire release | USD 0.98 billion | USD 8.94 billion (2036) | 24.7% (2026-2036) | [M3] |

The 2026 values span roughly 12×, which signals very high uncertainty. No single forecast should anchor a licensing valuation [M3][M6][M8]. Asia-Pacific is modeled as the largest region, with 70.0% of 2025 sales in one estimate. North America is modeled as the fastest-growing [M8][M3].

**Implications (analyst inference).**

- Incumbent silicon manufacturers are reported to be integrating tandem architectures into their existing high-volume manufacturing [M4][M5][M1].
- A university licensor competing on cell efficiency alone may therefore face strong pressure from these incumbents [M2][M4].
- Leading academic institutions cannot be identified from the academic sources, because the records lack affiliation data [A1][A2][A3].
- Academic patent holders in the sample include KFUPM and UNC/ASU [P1][P2][P6][P7].

## 5. Commercialization Opportunities & Recommendations

**Assessment mode: decision_support.**

**Decision under review.** Per the supplied decision context, the TTO is deciding whether to license a lab-scale perovskite-silicon tandem technology from a university research group. The target application is utility-scale PV modules. Sections 1-4 set out the evidence for this decision [A1][A3][M7].

**Responsible decision owner.** Technology transfer office, as supplied in the decision context.

**Primary commercialization route: out-license to an established crystalline-silicon module manufacturer or tandem module developer, with a utility-scale field of use [M1][M4][M7].**

Why this route is preferred (analyst inference):

- Recent academic work emphasizes compatibility with silicon heterojunction bottom cells and with industrial silicon [A3][A1].
- Incumbents are reported to be integrating tandems into their existing silicon manufacturing [M4][M5].
- So far, established manufacturers are the ones that have demonstrated full-size tandem modules [M1][M7].
- Together, this suggests that a lab-scale university asset could reach utility-scale modules mainly by being absorbed into an existing manufacturer's process, rather than by scaling up independently [M1][M4][M7].
- Exclusivity structure, royalty terms and licensee identity are **not established** in the evidence [M1][M4][M7].

**Alternatives (secondary).**

- **University spin-out.**
  - The Noak spin-off with €5 million suggests that institute spin-outs do occur [M1]. This evidence is a single headline.
  - The capital and time needed to reach utility-scale manufacturing are not established. Incumbents' scale advantages may also put a new entrant at a disadvantage in commodity utility volumes [M1][M4][M3][M8].
- **Sponsored research or an option agreement with an industrial partner before any license.**
  - This could fund the missing stability and scale-up evidence [A1][A3].
  - It is less attractive as an end state because it delays value capture. However, it is consistent with the DEFER conclusion below as an interim step (analyst inference) [A1][A3].
- **Licensing for a niche segment (premium residential or specialty) instead of utility.**
  - Early evidence exists for these segments [M1][M7].
  - This falls outside the supplied target application, and the owner would need to redefine the decision [M1][M7].

**Gated action plan.**

No success criteria were supplied. Every threshold below is an **analyst proposal requiring owner confirmation**, not an owner-approved gate. Cited benchmarks are external evidence and do not imply owner approval [A1][A3].

| Gate | Evidence needed | Proposed decision criterion (analyst proposal; owner confirmation required) | Basis | Source |
|---|---|---|---|---|
| G1. Asset definition and performance | Device area, architecture and independently certified efficiency of the asset | Proposed pass: independent certification exists for a defined device area. Comparisons should be like-for-like by architecture and area, for example a 1 cm² monolithic cell against the published 32.73% 1 cm² result. Any numeric competitiveness threshold is **not established** and is for the owner to set | External benchmark only | [A3][A5] |
| G2. Stability under a disclosed protocol | For the asset: encapsulation status, temperature, atmosphere, metric (T80 versus % retained) and duration | Proposed pass: MPP stability data reported with the full protocol disclosed. Duration should be comparable to published lab benchmarks, for example encapsulated MPP at 65 °C for about 1000 h, where 88% retention was reported. Any numeric retention threshold is a proposal only. Comparisons across different protocols are not valid | External benchmark; protocols not comparable across studies | [A1][A3] |
| G3. Reproducibility of the wide-bandgap film | Batch-to-batch data on phase homogeneity and efficiency spread | Proposed pass: the research group supplies reproducibility data across multiple batches. The acceptable spread is **not established** | Identified technical barrier | [A1][A6] |
| G4. IP position | The asset's own filings, claims and legal status; claims review against at least P1, P2, P6 and P7 (plus P3, P4 and P8 if relevant to the asset's architecture) | Proposed pass: counsel finds no claims in the reviewed records that block the asset's architecture without a licensable or design-around route. A comprehensive, jurisdiction-specific search is required | Snippet-level evidence only | [P1, P2, P3, P4, P5, P6, P7, P8] |
| G5. Licensee interest | Expressions of interest from manufacturers | Proposed pass: at least one qualified manufacturer requests an evaluation or option agreement. The evidence contains no sign of demand for this specific asset | Market signals only | [M1][M4][M7] |
| G6. Path to scale and durability | Large-area or mini-module data; damp-heat or certification-style reliability data | Proposed pass: a credible plan or partner exists to generate these data. The evidence contains no module, field, yield or cost data for any academic device | Evidence gap | [A1][A3][M6] |

**Proposed stop / kill criteria (analyst proposals requiring owner confirmation).**

- Stop if the asset has neither an independently certified efficiency nor stability data under a disclosed MPP protocol [A1][A3].
- Stop if counsel identifies blocking third-party claims with no licensable or design-around route [P1, P2, P3, P4, P5, P6, P7, P8].
- Stop if the asset's process is incompatible with industrial silicon bottom cells, such as HJT cells or textured wafers. That compatibility appears to underpin the route of integration by incumbents [A3][P2][P7][M4].

**Cost and time.**

- License valuation, royalty rates, patent-prosecution budget and capital requirement: **not established** in the decision context or the cited evidence [M3][M6][M8].
- Time to utility-scale deployment by a licensee: **not established** [M1].
- The only scheduled date in the evidence is Hanwha's end-2028 mass-production target. It is a third-party headline, not a timeline for this asset [M1].

**Opportunity notes (analyst inference; low confidence).**

- **Durability may be a differentiator.** Validation of durability, bankability and reliability appears underserved in the evidence [M6][M1][M5]. A university asset with strong stability data might therefore be more licensable than one differentiated on efficiency alone [A1][A3].
- **Capacity outside China.** Gigawatt-scale capacity outside China appears unresolved [M5][M7][M4]. This could shape which licensees are interested. However, no policy or procurement evidence confirms demand for non-Chinese supply [M3][M8].

**Decision applicability and conclusion: DEFER.**

This report recommends DEFER on the decision to license the technology for utility-scale modules, based on four evidence conditions [A1][A3][M6][P1, P2, P3, P4, P5, P6, P7, P8]:

1. The asset's certified performance, stability protocol, reproducibility and IP status are not in the validated evidence [A1][A3][P1, P2, P3, P4, P5, P6, P7, P8].
2. Field-level durability, yield and cost data are absent across all evidence domains. These appear to be the main bankability hurdles for utility use [A1][A3][M6].
3. The patent evidence is snippet-level, and legal status is unverified [P1, P2, P3, P4, P5, P6, P7, P8].
4. The market evidence consists of medium-credibility estimates that diverge widely [M3][M6][M8].

The decision could move to GO if gates G1, G2 and G4 pass under criteria the owner has confirmed. It could move to NO_GO if any proposed stop criterion is triggered [A1][A3][P1, P2, P3, P4, P5, P6, P7, P8].

## Evidence Limitations
- **Academic sources.**
  - Only 8 sources, assessed from abstracts only.
  - No author or affiliation data.
  - No module, field, cost or yield data.
  - Stability protocols differ across studies.
  - Two foundational sources concern single-junction cells rather than tandems.
  - The A7 record combines two papers.
  - A4 is low credibility and was excluded from conclusions.
- **Patent sources.**
  - Eight Google Patents search snippets only.
  - Legal status, claim scope and ownership are unverified.
  - Several records are applications or WO publications with unknown national-phase status.
  - White-space observations reflect absence within this small sample only.
- **Market sources.**
  - All are medium credibility at best. There are no primary filings, government procurement records or verified funding documents.
  - M2 and M5 are unverified company-style content, and M2 contains a questionable statement about silicon's efficiency limit.
  - Market estimates cover the broad perovskite market, use undisclosed methods and diverge widely.
  - The Noak and Hanwha items are headlines only.
  - Oxford PV's production timeline is conflicting.
- **Regulatory scope.** The validated sources include no stand-alone government or standards-body document. Third-party certifications (TÜV SÜD, Fraunhofer CalLab) appear only as reported in trade or company-style sources. Regulatory and certification requirements for utility-scale procurement were therefore not assessed in depth.
- **The specific asset.** No evidence describes the university asset's performance, IP or development stage beyond the decision context's "lab-scale" description.

## References

*Reference codes: **A** = Academic paper · **P** = Patent · **M** = Market/industry source*

[A1] Colloidally Prepared Homogeneous Wide-Bandgap Perovskites for Efficient Tandem Solar Cells with Industrial Silicon. Journal of the American Chemical Society. Published: 2026-11-15. Accessed: 2026-11-20. Type: academic_paper. Credibility: high. Rationale: OpenAlex record: DOI resolves; journal record (peer-review status not independently verified). Newly published (5d ago); 0 citations is expected, not a quality signal.. https://doi.org/10.1021/jacs.6c10873

[A2] Characterizing Fill Factor Limitations in Perovskite‐Silicon Tandem Solar Cells. Advanced Energy Materials. Published: 2026-11-10. Accessed: 2026-11-20. Type: academic_paper. Credibility: high. Rationale: OpenAlex record: DOI resolves; journal record (peer-review status not independently verified), 1 citations.. https://doi.org/10.1002/aenm.71802

[A3] Electrostatic Cation Intercalation Into Polymeric Self‐Assembled Monolayers Enables Ambient‐Air Fabrication of 32.73% Efficient Monolithic Perovskite/Silicon Tandem Solar Cells. Angewandte Chemie International Edition. Published: 2026-11-08. Accessed: 2026-11-20. Type: academic_paper. Credibility: high. Rationale: OpenAlex record: DOI resolves; journal record (peer-review status not independently verified). Newly published (12d ago); 0 citations is expected, not a quality signal.. https://doi.org/10.1002/anie.4438070

[A4] Technical Specification of the PSC-1 Tandem Lattice: High-Efficiency Solar Cells via 360-Qubit Distributed QPU Grid and Perovskite-Silicon Bandgap Alignment. Zenodo (CERN European Organization for Nuclear Research). Published: 2026-11-07. Accessed: 2026-11-20. Type: academic_paper. Credibility: low. Rationale: General-purpose repository deposit (Zenodo): no editorial screening or peer review; citations: 0. Do not rely on it for material conclusions without independent corroboration.. https://doi.org/10.5281/zenodo.24043009

[A5] Monolithic perovskite/silicon tandem solar cell with >29% efficiency by enhanced hole extraction. Science. Published: 2020-12-10. Accessed: 2026-11-20. Type: academic_paper. Credibility: high. Rationale: OpenAlex record: DOI resolves; journal record (peer-review status not independently verified), 2,282 citations.. https://doi.org/10.1126/science.abd4016

[A6] A mixed-cation lead mixed-halide perovskite absorber for tandem solar cells. Science. Published: 2016-01-07. Accessed: 2026-11-20. Type: academic_paper. Credibility: high. Rationale: OpenAlex record: DOI resolves; journal record (peer-review status not independently verified), 3,260 citations.. https://doi.org/10.1126/science.aad5845

[A7] Incorporation of rubidium cations into perovskite solar cells improves photovoltaic performance. Science. Published: 2016-09-29. Accessed: 2026-11-20. Type: academic_paper. Credibility: high. Rationale: OpenAlex record: DOI resolves; journal record (peer-review status not independently verified), 3,922 citations.. https://doi.org/10.1126/science.aah5557

[A8] Efficient and stable solution-processed planar perovskite solar cells via contact passivation. Science. Published: 2017-02-02. Accessed: 2026-11-20. Type: academic_paper. Credibility: high. Rationale: OpenAlex record: DOI resolves; journal record (peer-review status not independently verified), 2,422 citations.. https://doi.org/10.1126/science.aai9081

[P1] US11437537B2 - Perovskite-silicon tandem solar cell - Google Patents. King Fahd University of Petroleum and Minerals. Published: 2022-09-06. Accessed: 2026-11-20. Type: patent. Credibility: medium. Rationale: Secondary patent aggregator record; verify bibliographic and legal status against the issuing office; publication year: 2019; legal scope still requires claim review. Applicant: as listed by Google Patents, which notes its list may be inaccurate; not a legal title search.. https://patents.google.com/patent/US11437537B2/en

[P2] US20250248296A1 - Defect engineering in wide bandgap perovskites for efficient and stable fully textured perovskite-silicon tandem solar cells - Google Patents. University of North Carolina at Chapel Hill. Published: 2025-07-31. Accessed: 2026-11-20. Type: patent. Credibility: medium. Rationale: Secondary patent aggregator record; verify bibliographic and legal status against the issuing office; publication year: 2025; legal scope still requires claim review. Applicant: as listed by Google Patents, which notes its list may be inaccurate; not a legal title search.. https://patents.google.com/patent/US20250248296A1/en?oq=18%2F833670

[P3] AU2024406053A1 - Perovskite-silicon tandem solar cell and preparation method therefor - Google Patents. Chint New Energy Technology Co Ltd. Published: 2026-07-02. Accessed: 2026-11-20. Type: patent. Credibility: medium. Rationale: Secondary patent aggregator record; verify bibliographic and legal status against the issuing office; legal scope still requires claim review. Applicant: as listed by Google Patents, which notes its list may be inaccurate; not a legal title search.. https://patents.google.com/patent/AU2024406053A1/en

[P4] WO2022066707A1 - Methods and devices for integrated tandem solar module fabrication - Google Patents. Caelux Corp. Published: 2022-03-31. Accessed: 2026-11-20. Type: patent. Credibility: medium. Rationale: Secondary patent aggregator record; verify bibliographic and legal status against the issuing office; publication year: 2022; legal scope still requires claim review. Applicant: as listed by Google Patents, which notes its list may be inaccurate; not a legal title search.. https://patents.google.com/patent/WO2022066707A1/en

[P5] US9653696B2 - Tin perovskite/silicon thin-film tandem solar cell - Google Patents. SOLAR-TECTIC LLC. Published: 2017-05-16. Accessed: 2026-11-20. Type: patent. Credibility: medium. Rationale: Secondary patent aggregator record; verify bibliographic and legal status against the issuing office; legal scope still requires claim review. Applicant: as listed by Google Patents, which notes its list may be inaccurate; not a legal title search.. https://patents.google.com/patent/US9653696B2/en

[P6] US11756744B1 - Three-tandem perovskite/silicon-based tandem solar cell - Google Patents. King Fahd University of Petroleum and Minerals. Published: 2023-09-12. Accessed: 2026-11-20. Type: patent. Credibility: medium. Rationale: Secondary patent aggregator record; verify bibliographic and legal status against the issuing office; legal scope still requires claim review. Applicant: as listed by Google Patents, which notes its list may be inaccurate; not a legal title search.. https://patents.google.com/patent/US11756744B1/en

[P7] WO2021030491A1 - Perovskite/silicon tandem photovoltaic device - Google Patents. University of North Carolina at Chapel Hill; Arizona State University; Arizona State University Downtown Phoenix campus. Published: 2021-02-18. Accessed: 2026-11-20. Type: patent. Credibility: medium. Rationale: Secondary patent aggregator record; verify bibliographic and legal status against the issuing office; publication year: 2021; legal scope still requires claim review. Applicant: as listed by Google Patents, which notes its list may be inaccurate; not a legal title search.. https://patents.google.com/patent/WO2021030491A1/en

[P8] WO2024097417A1 - Encapsulated perovskite modules and solar cells containing the same - Google Patents. Caelux Corp. Published: 2024-05-10. Accessed: 2026-11-20. Type: patent. Credibility: medium. Rationale: Secondary patent aggregator record; verify bibliographic and legal status against the issuing office; publication year: 2024; legal scope still requires claim review. Applicant: as listed by Google Patents, which notes its list may be inaccurate; not a legal title search.. https://patents.google.com/patent/WO2024097417A1/en

[M1] Trina Solar secures first commercial order for perovskite-silicon tandem modules | Perovskite-Info. Perovskite Info. Published: 2026-06-19. Accessed: 2026-11-20. Type: reputable_news. Credibility: medium. Rationale: Specialist trade publication; useful but not an independent primary record.. https://www.perovskite-info.com/trina-solar-secures-first-commercial-order-perovskite-silicon-tandem-modules

[M2] Perovskite Tandem Solar Cells: Efficiency Breakthrough and First Commercial Modules. Thesmartere. Published: n.d.. Accessed: 2026-11-20. Type: company_disclosure. Credibility: medium. Rationale: Company-style content candidate inferred from URL shape; ownership and first-party attribution are unverified. Corroborate claims at the original source.. https://www.thesmartere.in/news/perovskite-tandem-solar-cells

[M3] Perovskite Solar Cells Market Size, Share, Trends, and. Globenewswire. Published: 2026-11-10. Accessed: 2026-11-20. Type: market_report. Credibility: medium. Rationale: Market-estimate release carried by www.globenewswire.com; counted as a commercial market estimate, not as reporting or a company disclosure. Press release wire service; primary for attributed company announcements.. https://www.globenewswire.com/news-release/2026/11/10/3399891/28124/en/perovskite-solar-cells-market-size-share-trends-and-global-forecast-to-2036-market-to-reach-8-94-billion-at-24-7-cagr-as-tandem-cells-bipv-and-roll-to-roll-manufacturing-scale.html

[M4] Tandem Solar Cell Market Size, Share | Growth Report [2034]. Fortunebusinessinsights. Published: n.d.. Accessed: 2026-11-20. Type: market_report. Credibility: medium. Rationale: Commercial market estimate with potentially proprietary methodology.. https://www.fortunebusinessinsights.com/tandem-solar-cell-market-116001

[M5] Perovskite-Silicon Tandem Solar Cell Technology Landscape 2026 — PatSnap Insights. Patsnap. Published: 2026-04-01. Accessed: 2026-11-20. Type: company_disclosure. Credibility: medium. Rationale: Company-style content candidate inferred from URL shape; ownership and first-party attribution are unverified. Corroborate claims at the original source.. https://www.patsnap.com/resources/blog/articles/perovskite-silicon-tandem-solar-cells-hit-34-in-2026

[M6] Perovskite Solar Cell Market Companies, Size & Trends 2026-2035. Precedenceresearch. Published: n.d.. Accessed: 2026-11-20. Type: market_report. Credibility: medium. Rationale: Commercial market estimate with potentially proprietary methodology.. https://www.precedenceresearch.com/perovskite-solar-cell-market

[M7] Oxford PV announces the first commercial deployment of a perovskite tandem solar panel | Perovskite-Info. Perovskite Info. Published: 2024-09-06. Accessed: 2026-11-20. Type: reputable_news. Credibility: medium. Rationale: Specialist trade publication; useful but not an independent primary record.. https://www.perovskite-info.com/oxford-pv-announces-first-commercial-deployment-perovskite-tandem-solar-panel

[M8] Perovskite Solar Cell Market to Reach USD 1.73 Billion by 2035 as Tandem Modules Move Toward Commercial Deployment. Yahoo. Published: 2026-10-19. Accessed: 2026-11-20. Type: market_report. Credibility: medium. Rationale: Market-estimate release carried by finance.yahoo.com; counted as a commercial market estimate, not as reporting or a company disclosure. Financial news host finance.yahoo.com; content may be syndicated. Hosting does not establish the original release author or first-party company provenance. Verify attribution and claims against the original source.. https://finance.yahoo.com/energy/articles/perovskite-solar-cell-market-reach-181100005.html