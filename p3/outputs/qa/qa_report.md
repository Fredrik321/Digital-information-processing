# QA report

Files checked: 811 (AMERICAN GOLDFINCH: 143, BARN OWL: 129, CARMINE BEE-EATER: 131, DOWNY WOODPECKER: 137, EMPEROR PENGUIN: 139, FLAMINGO: 132)

| check | result |
|---|---|
| zero-byte files | 0 |
| undecodable files | 0 |
| not RGB before conversion | 0 |
| constant (blank) images | 0 |
| files with EXIF metadata | 0 |
| pixel range | 0-255 |
| images reaching 0 / 255 | 742 / 671 |
| per-image mean (min / median / max) | 43.32 / 118.68 / 243.54 |
| per-image std (min / median / max) | 25.55 / 56.17 / 98.13 |
| file size, bytes (min / median / max) | 6,067 / 19,202 / 35,493 |
| exact byte duplicates (groups) | 0 |
| exact pixel duplicates (groups) | 0 |
| near-duplicate candidates (64-bit dHash, Hamming distance <= 12) | 35 |
| near-duplicate pairs confirmed by review | 24 |
| duplicate groups / files in them / redundant copies | 17 / 38 / 21 |
| cross-class candidates / confirmed | 3 / 0 |
| Pillow verify() failures | 0 |
| full-decode failures | 0 |
| missing JPEG end marker (truncation) | 0 |
| formats / modes / sizes | {'JPEG': 811} / {'RGB': 811} / {'224x224': 811} |
| JPEG quality (IJG table match) | {'95': 811} |

## Near-duplicate candidates

dHash distance histogram over all pairs: {'<=0': 2, '<=2': 4, '<=4': 8, '<=6': 15, '<=8': 19, '<=10': 24, '<=12': 35}

| distance band | pairs | duplicates | unreviewed |
|---|---|---|---|
| 0-6 | 15 | 15 | 0 |
| 7-10 | 9 | 7 | 0 |
| 11-12 | 11 | 2 | 0 |

| # | a | b | distance | verdict | reviewed by |
|---|---|---|---|---|---|
| 1 | EMPEROR PENGUIN/125.jpg | EMPEROR PENGUIN/136.jpg | 0 | duplicate |  |
| 2 | EMPEROR PENGUIN/128.jpg | EMPEROR PENGUIN/139.jpg | 0 | duplicate |  |
| 3 | FLAMINGO/005.jpg | FLAMINGO/026.jpg | 1 | duplicate |  |
| 4 | FLAMINGO/015.jpg | FLAMINGO/027.jpg | 1 | duplicate |  |
| 5 | BARN OWL/007.jpg | BARN OWL/060.jpg | 3 | duplicate |  |
| 6 | AMERICAN GOLDFINCH/011.jpg | AMERICAN GOLDFINCH/046.jpg | 4 | duplicate |  |
| 7 | DOWNY WOODPECKER/025.jpg | DOWNY WOODPECKER/056.jpg | 4 | duplicate |  |
| 8 | EMPEROR PENGUIN/058.jpg | EMPEROR PENGUIN/069.jpg | 4 | duplicate |  |
| 9 | DOWNY WOODPECKER/129.jpg | DOWNY WOODPECKER/130.jpg | 5 | duplicate |  |
| 10 | EMPEROR PENGUIN/040.jpg | EMPEROR PENGUIN/058.jpg | 5 | duplicate |  |
| 11 | EMPEROR PENGUIN/040.jpg | EMPEROR PENGUIN/069.jpg | 5 | duplicate |  |
| 12 | AMERICAN GOLDFINCH/063.jpg | AMERICAN GOLDFINCH/135.jpg | 6 | duplicate |  |
| 13 | CARMINE BEE-EATER/010.jpg | CARMINE BEE-EATER/023.jpg | 6 | duplicate |  |
| 14 | CARMINE BEE-EATER/013.jpg | CARMINE BEE-EATER/070.jpg | 6 | duplicate |  |
| 15 | EMPEROR PENGUIN/058.jpg | EMPEROR PENGUIN/089.jpg | 6 | duplicate |  |
| 16 | CARMINE BEE-EATER/031.jpg | CARMINE BEE-EATER/113.jpg | 7 | duplicate |  |
| 17 | EMPEROR PENGUIN/040.jpg | EMPEROR PENGUIN/089.jpg | 7 | duplicate |  |
| 18 | EMPEROR PENGUIN/051.jpg | EMPEROR PENGUIN/099.jpg | 7 | duplicate |  |
| 19 | BARN OWL/024.jpg | BARN OWL/028.jpg | 8 | duplicate |  |
| 20 | FLAMINGO/089.jpg | FLAMINGO/091.jpg | 9 | duplicate |  |
| 21 | BARN OWL/080.jpg | BARN OWL/110.jpg | 10 | different |  |
| 22 | CARMINE BEE-EATER/016.jpg | CARMINE BEE-EATER/081.jpg | 10 | duplicate |  |
| 23 | EMPEROR PENGUIN/014.jpg | EMPEROR PENGUIN/022.jpg | 10 | different |  |
| 24 | EMPEROR PENGUIN/069.jpg | EMPEROR PENGUIN/089.jpg | 10 | duplicate |  |
| 25 | CARMINE BEE-EATER/004.jpg | CARMINE BEE-EATER/016.jpg | 11 | duplicate |  |
| 26 | CARMINE BEE-EATER/066.jpg | EMPEROR PENGUIN/011.jpg | 11 | different |  |
| 27 | EMPEROR PENGUIN/037.jpg | EMPEROR PENGUIN/060.jpg | 11 | different |  |
| 28 | AMERICAN GOLDFINCH/072.jpg | AMERICAN GOLDFINCH/076.jpg | 12 | different |  |
| 29 | AMERICAN GOLDFINCH/115.jpg | BARN OWL/015.jpg | 12 | different |  |
| 30 | BARN OWL/033.jpg | BARN OWL/110.jpg | 12 | different |  |
| 31 | CARMINE BEE-EATER/010.jpg | CARMINE BEE-EATER/093.jpg | 12 | duplicate |  |
| 32 | DOWNY WOODPECKER/049.jpg | DOWNY WOODPECKER/051.jpg | 12 | different |  |
| 33 | EMPEROR PENGUIN/066.jpg | EMPEROR PENGUIN/116.jpg | 12 | different |  |
| 34 | EMPEROR PENGUIN/071.jpg | EMPEROR PENGUIN/105.jpg | 12 | different |  |
| 35 | EMPEROR PENGUIN/124.jpg | FLAMINGO/050.jpg | 12 | different |  |

Duplicate groups:

- AMERICAN GOLDFINCH/011.jpg, AMERICAN GOLDFINCH/046.jpg
- AMERICAN GOLDFINCH/063.jpg, AMERICAN GOLDFINCH/135.jpg
- BARN OWL/007.jpg, BARN OWL/060.jpg
- BARN OWL/024.jpg, BARN OWL/028.jpg
- CARMINE BEE-EATER/004.jpg, CARMINE BEE-EATER/016.jpg, CARMINE BEE-EATER/081.jpg
- CARMINE BEE-EATER/010.jpg, CARMINE BEE-EATER/023.jpg, CARMINE BEE-EATER/093.jpg
- CARMINE BEE-EATER/013.jpg, CARMINE BEE-EATER/070.jpg
- CARMINE BEE-EATER/031.jpg, CARMINE BEE-EATER/113.jpg
- DOWNY WOODPECKER/025.jpg, DOWNY WOODPECKER/056.jpg
- DOWNY WOODPECKER/129.jpg, DOWNY WOODPECKER/130.jpg
- EMPEROR PENGUIN/040.jpg, EMPEROR PENGUIN/058.jpg, EMPEROR PENGUIN/069.jpg, EMPEROR PENGUIN/089.jpg
- EMPEROR PENGUIN/051.jpg, EMPEROR PENGUIN/099.jpg
- EMPEROR PENGUIN/125.jpg, EMPEROR PENGUIN/136.jpg
- EMPEROR PENGUIN/128.jpg, EMPEROR PENGUIN/139.jpg
- FLAMINGO/005.jpg, FLAMINGO/026.jpg
- FLAMINGO/015.jpg, FLAMINGO/027.jpg
- FLAMINGO/089.jpg, FLAMINGO/091.jpg

Lowest-contrast images: FLAMINGO/129.jpg, CARMINE BEE-EATER/010.jpg, CARMINE BEE-EATER/023.jpg, FLAMINGO/123.jpg, CARMINE BEE-EATER/093.jpg
