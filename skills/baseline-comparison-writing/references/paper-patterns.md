# Primary-paper examples for baseline comparison writing

Consulted 2026-11-05. Selection favors directly relevant GIST studies and major
computational pathology papers in Nature Biomedical Engineering, Nature Medicine,
npj Precision Oncology and Cancer Research. This is a purposive writing sample,
not a systematic review, journal ranking, impact-factor claim or required citation
list. The rules in SKILL.md are our synthesis, not requirements issued by these
journals. No performance values from these examples are project results.

## CLAM — comparator roles, ablation and transfer are separate

Lu et al. (2021), *Data-efficient and weakly supervised computational pathology
on whole-slide images*. Nature Biomedical Engineering.
[DOI](https://doi.org/10.1038/s41551-020-00682-w) ·
[PMC author manuscript](https://pmc.ncbi.nlm.nih.gov/articles/PMC8711640/).

Read: Results on data efficiency (Fig. 2), paragraphs discussing MIL/mMIL and
same-label supervision; instance-clustering ablation paragraph pointing to
Supplementary Table 4; “Generalization to independent test cohorts” and Fig. 3.
The supplementary table itself was not inspected.

The text connects comparator choice to pooling and supervision assumptions,
discusses effects across training sizes, and distinguishes component removal from
independent-cohort evaluation. Repeated-model performance is shown rather than
relying only on a selected best model. Adaptation: give each comparison an
evidential role and report stability separately from the mechanism argument.

## UNI — isolate representation quality and qualify external rankings

Chen et al. (2024), *Towards a general-purpose foundation model for computational
pathology*. Nature Medicine.
[DOI](https://doi.org/10.1038/s41591-024-02857-3) ·
[PMC author manuscript](https://pmc.ncbi.nlm.nih.gov/articles/PMC11403354/).

Read: Methods paragraphs on pretrained encoder comparisons and weakly supervised
slide classification; Results Fig. 2 caption; Methods CAMELYON/PANDA comparison
notes pointing to Supplementary Tables 36–37. Those tables were not inspected.

Encoder alternatives are identified with architecture/pretraining differences.
The comparison uses shared patch coordinates and largely shared ABMIL settings,
and discusses pretraining overlap. Public-method comparisons carry explicit
qualifications about different features and MIL architectures. Adaptation:
specify the factor isolated by the internal experiment; keep published rankings
and differently resourced systems visibly distinct from that controlled contrast.

## GIST — compare against the existing clinical assessment

Fu et al. (2023), *Deep learning predicts patients outcome and mutations from
digitized histology slides in gastrointestinal stromal tumor*.
npj Precision Oncology 7, 71.
[DOI](https://doi.org/10.1038/s41698-023-00421-9) ·
[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10366108/).

Read: Results on survival prediction and cross-centre findings; Methods
“Prognostic model” and “Baseline models”; Discussion. Full-text XML retrieved
from the public Europe PMC endpoint when browser retrieval was intermittent.

The study sets image-only and image-plus-clinical models against Miettinen-based
assessment, explains their inputs and uses common fold splits/repeats for
baselines. Internal and independent-centre findings are reported separately,
including reduced transfer performance. Adaptation: tie the baseline to the
clinical question, name information differences, and report discordant external
findings. Its survival endpoint must not be ranked against risk-classification
AUC in another cohort. This is not endorsement of every analytical choice.

## Multicentre GIST — preserve a strong comparator and mixed findings

Bonetti, Le et al. (2026), *Deep Learning Predicts Mutations and Outcomes in
Gastrointestinal Stromal Tumors*. Cancer Research 86, 4175–4186.
[DOI](https://doi.org/10.1158/0008-5472.CAN-26-0132) ·
[PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC13473859/).

Read: Methods prognostic-model comparison/statistical analysis; Results Fig. 3
and Table 5 with its caption, and cohort-specific interpretation. Full-text XML
retrieved via Europe PMC. Referenced supplementary tables were not inspected.

Five prognostic models give image, integrated and pathology-based comparators
distinct roles. Shared covariate adjustment is described, and results are
organized by treatment cohort and validation setting with intervals. The account
retains stronger pathology-based external performance and subgroup exceptions.
Adaptation: show the strongest relevant comparator, separate cohort-dependent
findings, and distinguish an independent prognostic association from added
predictive value or universal superiority.

## Transfer into a manuscript

Together these examples suggest a useful writing sequence: comparison purpose →
comparator role and actual protocol → quantitative contrast with uncertainty →
stability/generalization → bounded interpretation in the literature. This is a
writing pattern, not authority to reproduce their experiment matrices. Follow
the user's existing study scope and evidence; no fixed comparator count, mandated
clinical dataset, positive result, or additional training is implied.
