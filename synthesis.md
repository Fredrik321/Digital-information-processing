# Portfolio synthesis (one page)

**IDIG4120 · Aksel Wiersdalen and Fredrik Svendsrud · 9 November 2026**
Dataset: "Bird Speciees Dataset" (Rahma Sleam, Kaggle v1, Apache 2.0) · Reports: `p1/p1.md`, `p2/p2.md`, `p3/p3.md` · Repository: <https://github.com/Fredrik321/Digital-information-processing>

## 1 · Which dataset, and which question does the project answer?

The **Bird Speciees Dataset** (Rahma Sleam, Kaggle v1, 29 September 2024, Apache 2.0): 811 JPEG images of six bird species, 129–143 per class, all 224×224 RGB `uint8`, totalling 122,078,208 raw bytes against 15,967,831 on disk, because every file was JPEG-encoded at quality 95 before we received it. Our project answers one question in three steps: **is this dataset fit for use, and can every claim we make about it be verified by someone else?** P1 characterised the data (format, sampling, frequency content, and how much species information the spectrum carries: a spectrum-only random forest reached 46.8 % against 16.7 % for guessing). P2 built a lossless codec on that baseline. P3 packaged dataset and codec as a verifiable product and recorded the verdict.

## 2 · How did each part shape the next?

A P1 choice constrained the P2 codec directly: P1's loader fixed the baseline as the (811, 224, 224, 3) `uint8` array of JPEG-**decoded** pixels. That stream is close to random at the byte level (entropy 7.648 bits/byte), so zero-order Huffman alone barely compressed it (ratio 1.04), which forced P2 to add horizontal/vertical delta predictors and a PNG path. It also means every P2 ratio describes JPEG-decoded pixels, not camera originals. P1's loader also called `.convert("RGB")`, which would silently mask a wrong colour mode; P3's validator rejects such a file instead (p3.md §2). P2's feedback became P3's brief: zlib got the same container framing, the two development images became all 811, and P2's quadratic bit-packer was rewritten to run 90–165× faster (p3.md §7). P1's concerns became P3's measurements: the background effect is now visible in per-class compression ratios (p3.md §9), and the 21 duplicates P3 found put a caveat on P1's 46.8 % classifier result (p3.md §10).

## 3 · Strongest evidence and main limitation

**Strongest evidence:** P3's verification chain, namely a SHA-256 manifest for all 811 files checkable with standard `sha256sum` (no code of ours), 4,055 exact codec round trips over the full dataset, and a reference check that reproduces P2's reported sizes to the byte, re-confirmed in a fresh environment with identical output digests. P2's entropy analysis backs it: the Huffman payload sits within 0.26 % of the zero-order entropy bound, so the coder, not chance, produced the numbers. **Main limitation, common to all three parts: provenance.** Who took the photographs and where they came from is unknown, so labels, preprocessing history and rights rest on an input we cannot verify.

## 4 · Is the dataset fit for use?

**Use with controls** in the course: verify the manifest, report results per image and per class, de-duplicate before any train/test split, keep the attribution (p3.md §1). Outside the course: **investigate** first. The licence is declared, not verified, because the upstream source of the photographs is unknown (p3.md §10). What would change it: identifying the upstream source and confirming the rights would move the outside-course verdict to *use with controls*; a duplicate review beyond our dHash-12 threshold, and re-running the P1 classifier afterwards, would settle whether 46.8 % is inflated.

## 5 · What is still unresolved?

The upstream source and rights of the photographs (the largest open problem); how many near-duplicates lie beyond the dHash-12 threshold (21 is a lower bound); whether P1's 46.8 % is inflated by those duplicates (not re-run); representativeness (six curated species, drawings among photographs, systematic background differences, unknown capture conditions); and the P3 schema sees structure, not meaning: a mislabelled bird still passes validation.

## AI declaration

As declared in each report, AI was used primarily for code generation: most of the code across all three parts was AI-written, then adjusted and reviewed by us. It also assisted with interpreting the tasks, structuring and drafting text. For P3, Claude (Anthropic, via Claude Code) also ran the experiments and proposed the near-duplicate verdicts, which we confirmed by eye. We checked the reported numbers against the committed outputs, edited all text, and take responsibility for the results. This synthesis was drafted with AI assistance and reviewed by us.
