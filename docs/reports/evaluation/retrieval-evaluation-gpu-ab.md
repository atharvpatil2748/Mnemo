# Identity-Bound Phase 8.6 GPU Reranker A/B

**Status:** VALID GPU A/B  
**Promotion decision:** **NEEDS MORE EVIDENCE**

## 1. Executive summary

The corrected 70-query, document/version-identity-bound K=50 experiment completed for both rerankers on the RTX 4060. BGE improved 31 raw query ranks, regressed 18, and left 21 unchanged. It improved every aggregate metric, including R@1 from 0.243 to 0.329. It nevertheless lost eight ms-marco rank-1 successes, and corrected Phase 8.5 Golden evidence is absent; promotion is therefore not authorized.

## 2. Evaluation validity

- Result status `VALIDATION_PASS`; `full_benchmark_run=true`.
- Both models: 70/70 unique QIDs; checkpoint `COMPLETE` with 70/70 each.
- Same query, target, candidate identity/order, semantic text, and K=50 pool digest were asserted for both rerankers.
- Relevance is canonical document/version identity at chunk-ranked positions, not title or filename matching.
- Protected-state comparison passed. No OOM retry or CPU fallback occurred.

## 3. Environment and identities

- Python: `3.12.10 (tags/v3.12.10:0cc8128, Apr  8 2025, 12:21:36) [MSC v.1943 64 bit (AMD64)]`
- PyTorch/CUDA: `2.13.0+cu130` / `13.0`
- GPU: `NVIDIA GeForce RTX 4060 Laptop GPU`
- Database: `C:\Users\athar\Desktop\Mnemo\data\canonical_production\mnemo_canonical.db`
- Database SHA-256: `dc9e7fa2d1cb77f0e42ec3220377f74b1e2f98842acbfe487d1c7e6502fb2ada`
- Query-set SHA-256: `dc614edd6280d18f7fc64403b14f5feaceb0f0963901d9dfec73a6b01a606fab`
- Manifest SHA-256: `05dbd17e100b3a8eb6e802e16de1440d695047c1b9c560dc10efc951c9ce982e`
- Candidate protocol/K/RRF-k: `forensic-v1` / 50 / 60
- ms-marco revision: `233902d25c440f23af6f7d6e94d2946bac0bee0a`
- BGE revision: `953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`

## 4. Overall metrics

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 70 | 0.243 | 0.400 | 0.657 | 0.349 | 0.410 |
| bge | 70 | 0.329 | 0.600 | 0.714 | 0.448 | 0.505 |

## 5. Metrics by language direction

### en->en

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 8 | 0.875 | 1.000 | 1.000 | 0.938 | 0.954 |
| bge | 8 | 0.875 | 0.875 | 1.000 | 0.896 | 0.920 |

### en->hi

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 15 | 0.133 | 0.200 | 0.733 | 0.248 | 0.348 |
| bge | 15 | 0.333 | 0.600 | 0.800 | 0.450 | 0.523 |

### en->mr

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 15 | 0.000 | 0.000 | 0.067 | 0.030 | 0.024 |
| bge | 15 | 0.067 | 0.267 | 0.333 | 0.155 | 0.195 |

### hi->hi

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 15 | 0.267 | 0.467 | 0.867 | 0.419 | 0.513 |
| bge | 15 | 0.467 | 0.867 | 0.867 | 0.605 | 0.660 |

### mr->mr

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 17 | 0.235 | 0.588 | 0.765 | 0.380 | 0.458 |
| bge | 17 | 0.176 | 0.529 | 0.706 | 0.356 | 0.431 |

## 6. Metrics by format

### csv

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| bge | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

### docx

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| bge | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

### html

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 34 | 0.147 | 0.353 | 0.765 | 0.287 | 0.388 |
| bge | 34 | 0.235 | 0.588 | 0.765 | 0.404 | 0.480 |

### json

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 1 | 0.000 | 1.000 | 1.000 | 0.500 | 0.631 |
| bge | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

### md

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| bge | 1 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

### pdf

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 28 | 0.179 | 0.286 | 0.429 | 0.255 | 0.281 |
| bge | 28 | 0.286 | 0.536 | 0.571 | 0.374 | 0.416 |

### pptx

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| bge | 2 | 0.500 | 0.500 | 1.000 | 0.583 | 0.678 |

### xlsx

| Group | N | R@1 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| ms-marco | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| bge | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

## 7. Candidate-pool coverage

| K | Target in pool | Coverage |
|---:|---:|---:|
| 25 | 54/70 | 77.1% |
| 50 | 60/70 | 85.7% |
| 100 | 62/70 | 88.6% |

The 16 K25 misses and their recoveries are:

| QID | Target | K25 rank | K50 rank | K100 rank |
|---|---|---:|---:|---:|
| DQ02 | mahades_economic_survey_highlights_marathi.pdf | — | — | — |
| DQ03 | mahades_economic_survey_ch1_marathi.pdf | — | — | — |
| DQ04 | mahades_economic_survey_ch1_marathi.pdf | — | — | — |
| DQ05 | mahades_economic_survey_ch2_marathi.pdf | — | — | — |
| DQ06 | mahades_economic_survey_ch2_marathi.pdf | — | — | — |
| DQ10 | shetkaryacha_asud_pan_2_marathi.html | — | — | 71 |
| DQ11 | shetkaryacha_asud_pan_3_marathi.html | — | 38 | 48 |
| DQ12 | shetkaryacha_asud_pan_3_marathi.html | — | — | — |
| DQ28 | rbi_annual_report_hindi_governance_2024.pdf | — | 46 | 57 |
| DQ31 | godan_chapter_2_hindi.html | — | 30 | 39 |
| DQ54 | CAND-FD-MR-HTML-01-shetkaryacha-asud.html | — | 34 | 38 |
| DQ55 | rbi_annual_report_hindi_payment_systems_2024.pdf | — | — | 75 |
| DQ59 | mahades_economic_survey_highlights_marathi.pdf | — | — | — |
| DQ60 | mahades_economic_survey_ch1_marathi.pdf | — | — | — |
| DQ61 | mahades_economic_survey_ch1_marathi.pdf | — | 49 | 49 |
| DQ62 | mahades_economic_survey_ch2_marathi.pdf | — | 31 | 31 |

K50 recovers six: DQ11, DQ28, DQ31, DQ54, DQ61, DQ62. K100 additionally recovers: DQ10, DQ55.

## 8. Paired changes

| Cutoff | BGE gains | BGE losses | Discordant | Exact two-sided binomial p |
|---|---:|---:|---:|---:|
| R@1 | 14 | 8 | 22 | 0.2863 |
| R@5 | 20 | 6 | 26 | 0.0094 |
| R@10 | 9 | 5 | 14 | 0.4240 |

Raw rank wins/regressions/unchanged: **31 / 18 / 21**.

## 9. Rank-1 regression forensics

For each ms-marco rank-1 loss, the target is the canonical document/version. The artifact proves BGE's within-model score ordering; it does not reveal a causal internal rationale.

### DQ16

- BGE target rank/score: `4` / `0.29462680220603943`
- BGE competing rank-1 title/score: `Microsoft Word - PREFACE_23_24_E_30524.doc` / `0.7671517729759216`
- Competitor evidence: Item 1960-61 1970-71 1980-81 1990-91 2000-01 2010-11 2020-21 2022-23 (1) (2) (3) (4) (5) (6) (7) (8) (9) A. Installed capacity (MW) A - 1 Installed Capacity in the State (1) Thermal 477$ 1,065$ 2,771 6,462 8,075 9,665 21…
- Target evidence: बेिसक ॲिनमल हÎबंडरी ÎटॅिटिÎटक्स - 2025 नुसार, सन 2024-25 मध्ये,  राज्य मांस उत्पादनात 11.6 टक्के िहÌÌयासह देशात ितसऱ्या कर्मांकावर  राज्यात दरडोई मांसाची उपलÅधता Ģितवषर् 9.5 िकलो  राज्य दूध उत्पादनात 6.7 टक्के िहÌÌयास…
- Finding: BGE assigned the competing semantic chunk a higher score than the canonical target chunk; the stored outputs do not establish a deeper causal model rationale.

### DQ22

- BGE target rank/score: `10` / `0.010533677414059639`
- BGE competing rank-1 title/score: `PHASE8_6_GENERALIZATION_TEST_REPORT.md` / `0.050795044749975204`
- Competitor evidence: | QID | Direction | Format | Target Document | Baseline Rank | Contextual Rank | Query Snippet | |---|---|---|---|---|---|---| | **DQ01** | `en->mr` | `.pdf` | `mahades_economic_survey_highlights_marathi.pdf` | 2 | **1**…
- Target evidence: दर चैत्नमासीं वर्षप्रतिपदेस भटब्राह्यण शेतकर्‍यांचे घरोघर वर्षफळ वाचून त्यांजपासून दक्षिणा घेतात. तसेंच रामनवमी व हनुमंतजयंतीचे निमित्तानें भटब्राह्यण आपले आळींत एकादा सधन शेतकरी असल्यास त्याजपासून अगर गरीबच सर्व असल्यास…
- Finding: BGE assigned the competing semantic chunk a higher score than the canonical target chunk; the stored outputs do not establish a deeper causal model rationale.

### DQ23

- BGE target rank/score: `34` / `0.0008172714151442051`
- BGE competing rank-1 title/score: `PHASE8_6_GENERALIZATION_TEST_REPORT.md` / `0.41388043761253357`
- Competitor evidence: | QID | Direction | Format | Target Document | Baseline Rank | Contextual Rank | Query Snippet | |---|---|---|---|---|---|---| | **DQ01** | `en->mr` | `.pdf` | `mahades_economic_survey_highlights_marathi.pdf` | 2 | **1**…
- Target evidence: सदरीं लिहिलेल्या एकंदर सर्व भटब्राह्यणांच्या धर्मरूमी चरकांतून शेतकर्‍यांची मस्ती जिरली नाहीं, तर भटब्राह्यण बदरीकेदार वगैरे तीर्थयात्नेचे नादीं लावून शेवटीं त्यांस कशीप्रयागास नेऊन तेथें त्यास हजारों रुपयास नागवून त्यां…
- Finding: BGE assigned the competing semantic chunk a higher score than the canonical target chunk; the stored outputs do not establish a deeper causal model rationale.

### DQ37

- BGE target rank/score: `5` / `0.34842240810394287`
- BGE competing rank-1 title/score: `rbi_annual_report_hindi_payment_systems_2024.pdf` / `0.7392582297325134`
- Competitor evidence: IX.38 वर्षष केे दौरान, केंंद्रीीय बैंंक डि�जि�ट ल मुुद्रा (सीबीडीीसी) की शुुरुआत, चलनि�धि� समाायोजन सुुवििdधाा (एलएएफ) केे तहत सुुवििdधााओंं को प्रति‍�‍वर्ती करना और एनईएफटी को आईएसओ 20022 माानक केे अनुुरूप बनानेे जैैसी …
- Target evidence: लि�ए और वििdत्तीय समावेेशन कोो गहन बनाानेे केे लि�ए, रि_ज़र्वव बैंंंक केे उप-कायाा�लय जूू न 2023 और अक्टूूबर 2023 मेंं क्रमशःः कोहि�माा (नागालैंंड) और ईटानगर (अरुणााचल प्रदेेश) मेंं खोलेे गए थेे। इसकेे साथ, रि_ज़र्वव बैं…
- Finding: BGE assigned the competing semantic chunk a higher score than the canonical target chunk; the stored outputs do not establish a deeper causal model rationale.

### DQ39

- BGE target rank/score: `2` / `0.7885782122612`
- BGE competing rank-1 title/score: `गो-दान/२` / `0.8391515016555786`
- Competitor evidence: ​ सेमरी और बेलारी दोनों अवध-प्रान्त के गाँव हैं। जिले का नाम बताने की कोई ज़रूरत नहीं। होरी बेलारी में रहता है, राय साहब अमरपाल सिंह सेमरी में। दोनों गाँवों में केवल पाँच मील का अन्तर है। पिछले सत्याग्रह-संग्राम में राय …
- Target evidence: होरी कदम बढ़ाये चला जाता था। पगडण्डी के दोनों ओर ऊख के पौधों की लहराती हुई हरियाली देख कर उसने मन में कहा—भगवान कहीं गौं से बरखा कर दें और डाँड़ी भी सुभीते से रहे, तो एक गाय जरूर लेगा। देशी गायें तो न दूध दें न उनके बछवे…
- Finding: BGE assigned the competing semantic chunk a higher score than the canonical target chunk; the stored outputs do not establish a deeper causal model rationale.

### DQ51

- BGE target rank/score: `2` / `0.5639710426330566`
- BGE competing rank-1 title/score: `PHASE8_6_GENERALIZATION_TEST_REPORT.md` / `0.9789819121360779`
- Competitor evidence: 1. **`[DQ19] mr -> mr .html`** - **Query:** *"विद्येविना मती गेली या प्रसिद्ध पंक्तींचा वापर करून फुल्यांनी शेतकऱ्यांचे अज्ञान कसे मांडले आहे?"* - **Target:** `CAND-FD-MR-HTML-01-shetkaryacha-asud.html` (Pan 1) - **Shift…
- Target evidence: आतां पहिले प्रकारचे अक्षरशून्य शेतकर्‍यांस भटब्राह्यण धर्ममिषानें इतकें नाडितात कीं, त्यांजविषय़ीं या जगांत दुसरा कोठें या मासल्याचा पडोसा सांपडणें फार कठीण. पूर्वीच्या धूर्त आर्यब्राह्यण ग्रंथकारांनीं आपले मतलबी धर्माचे…
- Finding: BGE assigned the competing semantic chunk a higher score than the canonical target chunk; the stored outputs do not establish a deeper causal model rationale.

### DQ56

- BGE target rank/score: `4` / `0.11003836989402771`
- BGE competing rank-1 title/score: `PHASE8_6_EVALUATION_REPORT.md` / `0.4164525866508484`
- Competitor evidence: | # | Filename | Lang | Script | Format | Size | Pages / Sections | Source / Provenance | |---|---|---|---|---|---|---|---| | 1 | `rbi_annual_report_hindi_payment_systems_2024.pdf` | Hindi | Devanagari | `.pdf` | 1.83 MB…
- Target evidence: सा रणी XI.2: 1 अपल्रै , 2023 - 31 मा र्चच, 2024 केे दौ रा न केंंद्री बो र ्डडकी समि�ति�यों की बठै क में उपस्थि�िति� सदस्य का ा नाम आरबी ीआई अधिVनि�यम , 1934 केे तहत नि�युु क्त/नामि�त आयो ोजि�त बैठकों क सखं ्य बैठकों की स…
- Finding: BGE assigned the competing semantic chunk a higher score than the canonical target chunk; the stored outputs do not establish a deeper causal model rationale.

### DQ64

- BGE target rank/score: `6` / `0.006937205791473389`
- BGE competing rank-1 title/score: `PHASE8_6_GENERALIZATION_TEST_REPORT.md` / `0.6169940829277039`
- Competitor evidence: | QID | Direction | Format | Target Document | Baseline Rank | Contextual Rank | Query Snippet | |---|---|---|---|---|---|---| | **DQ01** | `en->mr` | `.pdf` | `mahades_economic_survey_highlights_marathi.pdf` | 2 | **1**…
- Target evidence: Title: Slide 20 m GRADIENT DESCENT
- Finding: BGE assigned the competing semantic chunk a higher score than the canonical target chunk; the stored outputs do not establish a deeper causal model rationale.

## 10. All 70 per-query comparisons

| QID | Direction | Format | Target | ms rank | BGE rank | Δ (ms−BGE) | Outcome |
|---|---|---|---|---:|---:|---:|---|
| DQ01 | en->mr | pdf | mahades_economic_survey_highlights_marathi.pdf | 47 | 2 | 45 | BGE_IMPROVEMENT |
| DQ02 | en->mr | pdf | mahades_economic_survey_highlights_marathi.pdf | — | — | 0 | NO_CHANGE |
| DQ03 | en->mr | pdf | mahades_economic_survey_ch1_marathi.pdf | — | — | 0 | NO_CHANGE |
| DQ04 | en->mr | pdf | mahades_economic_survey_ch1_marathi.pdf | — | — | 0 | NO_CHANGE |
| DQ05 | en->mr | pdf | mahades_economic_survey_ch2_marathi.pdf | — | — | 0 | NO_CHANGE |
| DQ06 | en->mr | pdf | mahades_economic_survey_ch2_marathi.pdf | — | — | 0 | NO_CHANGE |
| DQ07 | en->mr | html | CAND-FD-MR-HTML-01-shetkaryacha-asud.html | 15 | 6 | 9 | BGE_IMPROVEMENT |
| DQ08 | en->mr | html | CAND-FD-MR-HTML-01-shetkaryacha-asud.html | 14 | 1 | 13 | BGE_IMPROVEMENT |
| DQ09 | en->mr | html | shetkaryacha_asud_pan_2_marathi.html | 6 | 3 | 3 | BGE_IMPROVEMENT |
| DQ10 | en->mr | html | shetkaryacha_asud_pan_2_marathi.html | — | — | 0 | NO_CHANGE |
| DQ11 | en->mr | html | shetkaryacha_asud_pan_3_marathi.html | 18 | 13 | 5 | BGE_IMPROVEMENT |
| DQ12 | en->mr | html | shetkaryacha_asud_pan_3_marathi.html | — | — | 0 | NO_CHANGE |
| DQ13 | mr->mr | pdf | mahades_economic_survey_highlights_marathi.pdf | 9 | 1 | 8 | BGE_IMPROVEMENT |
| DQ14 | mr->mr | pdf | mahades_economic_survey_highlights_marathi.pdf | 4 | 4 | 0 | NO_CHANGE |
| DQ15 | mr->mr | pdf | mahades_economic_survey_ch1_marathi.pdf | 4 | 13 | -9 | BGE_REGRESSION |
| DQ16 | mr->mr | pdf | mahades_economic_survey_ch1_marathi.pdf | 1 | 4 | -3 | BGE_REGRESSION |
| DQ17 | mr->mr | pdf | mahades_economic_survey_ch2_marathi.pdf | 13 | 32 | -19 | BGE_REGRESSION |
| DQ18 | mr->mr | pdf | mahades_economic_survey_ch2_marathi.pdf | 13 | 42 | -29 | BGE_REGRESSION |
| DQ19 | mr->mr | html | CAND-FD-MR-HTML-01-shetkaryacha-asud.html | 2 | 2 | 0 | NO_CHANGE |
| DQ20 | mr->mr | html | CAND-FD-MR-HTML-01-shetkaryacha-asud.html | 3 | 2 | 1 | BGE_IMPROVEMENT |
| DQ21 | mr->mr | html | shetkaryacha_asud_pan_2_marathi.html | 7 | 6 | 1 | BGE_IMPROVEMENT |
| DQ22 | mr->mr | html | shetkaryacha_asud_pan_2_marathi.html | 1 | 10 | -9 | BGE_REGRESSION |
| DQ23 | mr->mr | html | shetkaryacha_asud_pan_3_marathi.html | 1 | 34 | -33 | BGE_REGRESSION |
| DQ24 | mr->mr | html | shetkaryacha_asud_pan_3_marathi.html | 4 | 1 | 3 | BGE_IMPROVEMENT |
| DQ25 | en->hi | pdf | rbi_annual_report_hindi_payment_systems_2024.pdf | 1 | 1 | 0 | NO_CHANGE |
| DQ26 | en->hi | pdf | rbi_annual_report_hindi_payment_systems_2024.pdf | 6 | 1 | 5 | BGE_IMPROVEMENT |
| DQ27 | en->hi | pdf | rbi_annual_report_hindi_governance_2024.pdf | 20 | 4 | 16 | BGE_IMPROVEMENT |
| DQ28 | en->hi | pdf | rbi_annual_report_hindi_governance_2024.pdf | 2 | 1 | 1 | BGE_IMPROVEMENT |
| DQ29 | en->hi | html | CAND-FD-HI-HTML-01-godan.html | 28 | 1 | 27 | BGE_IMPROVEMENT |
| DQ30 | en->hi | html | CAND-FD-HI-HTML-01-godan.html | 6 | 7 | -1 | BGE_REGRESSION |
| DQ31 | en->hi | html | godan_chapter_2_hindi.html | 10 | 12 | -2 | BGE_REGRESSION |
| DQ32 | en->hi | html | godan_chapter_2_hindi.html | 8 | 3 | 5 | BGE_IMPROVEMENT |
| DQ33 | en->hi | html | godan_chapter_3_hindi.html | 8 | 6 | 2 | BGE_IMPROVEMENT |
| DQ34 | en->hi | html | godan_chapter_3_hindi.html | 6 | 9 | -3 | BGE_REGRESSION |
| DQ35 | hi->hi | pdf | rbi_annual_report_hindi_payment_systems_2024.pdf | 12 | 1 | 11 | BGE_IMPROVEMENT |
| DQ36 | hi->hi | pdf | rbi_annual_report_hindi_payment_systems_2024.pdf | 6 | 1 | 5 | BGE_IMPROVEMENT |
| DQ37 | hi->hi | pdf | rbi_annual_report_hindi_governance_2024.pdf | 1 | 5 | -4 | BGE_REGRESSION |
| DQ38 | hi->hi | pdf | rbi_annual_report_hindi_governance_2024.pdf | 11 | 1 | 10 | BGE_IMPROVEMENT |
| DQ39 | hi->hi | html | CAND-FD-HI-HTML-01-godan.html | 1 | 2 | -1 | BGE_REGRESSION |
| DQ40 | hi->hi | html | CAND-FD-HI-HTML-01-godan.html | 9 | 1 | 8 | BGE_IMPROVEMENT |
| DQ41 | hi->hi | html | godan_chapter_2_hindi.html | 7 | 4 | 3 | BGE_IMPROVEMENT |
| DQ42 | hi->hi | html | godan_chapter_2_hindi.html | 4 | 12 | -8 | BGE_REGRESSION |
| DQ43 | hi->hi | html | godan_chapter_3_hindi.html | 2 | 4 | -2 | BGE_REGRESSION |
| DQ44 | hi->hi | html | godan_chapter_3_hindi.html | 8 | 5 | 3 | BGE_IMPROVEMENT |
| DQ45 | hi->hi | html | CAND-FD-HI-HTML-01-godan.html | 1 | 1 | 0 | NO_CHANGE |
| DQ46 | hi->hi | html | godan_chapter_2_hindi.html | 2 | 11 | -9 | BGE_REGRESSION |
| DQ47 | hi->hi | html | godan_chapter_3_hindi.html | 7 | 1 | 6 | BGE_IMPROVEMENT |
| DQ48 | en->hi | html | CAND-FD-HI-HTML-01-godan.html | 10 | 1 | 9 | BGE_IMPROVEMENT |
| DQ49 | en->hi | html | godan_chapter_2_hindi.html | 16 | 13 | 3 | BGE_IMPROVEMENT |
| DQ50 | en->hi | html | godan_chapter_3_hindi.html | 8 | 3 | 5 | BGE_IMPROVEMENT |
| DQ51 | mr->mr | html | CAND-FD-MR-HTML-01-shetkaryacha-asud.html | 1 | 2 | -1 | BGE_REGRESSION |
| DQ52 | mr->mr | html | shetkaryacha_asud_pan_2_marathi.html | 5 | 2 | 3 | BGE_IMPROVEMENT |
| DQ53 | mr->mr | html | shetkaryacha_asud_pan_3_marathi.html | 7 | 1 | 6 | BGE_IMPROVEMENT |
| DQ54 | en->mr | html | CAND-FD-MR-HTML-01-shetkaryacha-asud.html | 15 | 4 | 11 | BGE_IMPROVEMENT |
| DQ55 | en->hi | pdf | rbi_annual_report_hindi_payment_systems_2024.pdf | — | — | 0 | NO_CHANGE |
| DQ56 | en->hi | pdf | rbi_annual_report_hindi_governance_2024.pdf | 1 | 4 | -3 | BGE_REGRESSION |
| DQ57 | hi->hi | pdf | rbi_annual_report_hindi_payment_systems_2024.pdf | 1 | 1 | 0 | NO_CHANGE |
| DQ58 | hi->hi | pdf | rbi_annual_report_hindi_governance_2024.pdf | 6 | 2 | 4 | BGE_IMPROVEMENT |
| DQ59 | en->mr | pdf | mahades_economic_survey_highlights_marathi.pdf | — | — | 0 | NO_CHANGE |
| DQ60 | en->mr | pdf | mahades_economic_survey_ch1_marathi.pdf | — | — | 0 | NO_CHANGE |
| DQ61 | mr->mr | pdf | mahades_economic_survey_ch1_marathi.pdf | 14 | 10 | 4 | BGE_IMPROVEMENT |
| DQ62 | mr->mr | pdf | mahades_economic_survey_ch2_marathi.pdf | 20 | 35 | -15 | BGE_REGRESSION |
| DQ63 | en->en | docx | engineering_lab_report_heat_transfer.docx | 1 | 1 | 0 | NO_CHANGE |
| DQ64 | en->en | pptx | ml_linear_regression.pptx | 1 | 6 | -5 | BGE_REGRESSION |
| DQ65 | en->en | pptx | ml_decision_tree.pptx | 1 | 1 | 0 | NO_CHANGE |
| DQ66 | en->en | xlsx | ons_uk_gdp_quarterly_tables.xlsx | 1 | 1 | 0 | NO_CHANGE |
| DQ67 | en->en | xlsx | ons_uk_consumer_price_inflation.xlsx | 1 | 1 | 0 | NO_CHANGE |
| DQ68 | en->en | csv | world_gdp_historical.csv | 1 | 1 | 0 | NO_CHANGE |
| DQ69 | en->en | json | world_countries_metadata.json | 2 | 1 | 1 | BGE_IMPROVEMENT |
| DQ70 | en->en | md | pep8_python_style_guide.md | 1 | 1 | 0 | NO_CHANGE |

## 11. GPU performance

- ms-marco: 3500 pairs in 22.19s; peak allocated 117,798,912 bytes.
- BGE: 3500 pairs in 670.29s; peak allocated 2,941,503,488 bytes, peak reserved 4,659,871,744 bytes.
- Requested/actual batch size: 2/2 for both; OOM retries: 0.

## 12. Historical comparison boundary

The earlier 24/70 canonical, 8/70 exact-title, and 19/70 identity-corrected saved-comprehensive top-1 counts mix matching and candidate/retrieval differences. They are not promotion metrics and are not compared numerically with this new paired run. This experiment fixes matching and freezes a shared candidate pool.

## 13. Limitations and bottlenecks

- Ten targets remain absent from K50; reranking cannot recover them.
- Eight of those remain outside K100, confirming a Stage-A retrieval/representation bottleneck.
- Phase 8.5 Golden was not run under this corrected harness.
- Multimodal retrieval was not evaluated.
- Candidate relevance is document/version-level, not chunk-specific qrels.
- Model scores are meaningful for ordering within a model, not as calibrated cross-model values.

## 14. Promotion decision

**NEEDS MORE EVIDENCE.** BGE is empirically stronger on aggregate Phase 8.6 metrics, particularly R@5, but this single N=70 run contains eight rank-1 regressions and lacks corrected Golden evidence. No production reranker change is authorized.

## 15. Recommended next experiment

Run exactly one corrected identity-bound **Phase 8.5 Golden A/B at K=50**, freezing the same candidate pool and changing only ms-marco versus BGE. Do not promote or begin contextual representation work until that controlled Golden check is reviewed.

## 16. Production safety

No reranker alias, production K, BGE-M3, embeddings, FTS, corpus, Golden Dataset, ContextBuilder, parser/chunking, database, or production configuration was changed by this analysis. No model inference was rerun.
