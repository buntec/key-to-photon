# Results: 2026-11-26

An iPhone 16 Plus filmed a MacBook Pro screen at 240 fps while `a` was typed
repeatedly. Cursor, VS Code, and Zed were measured in their built-in
terminals; btmux as an app and in Chrome. That makes 13 configurations of 12
apps, each recorded once on one machine, except cmux, herdr, and Zed
(twice). Every
event was checked by eye on the contact sheets.

| Terminal        | Version                         | n  | Mean        | Median | Std. dev. | Std. err. | Range       |
|-----------------|---------------------------------|----|-------------|--------|-----------|-----------|-------------|
| kitty           | 0.51.1                          | 17 | **58.5 ms** | 58.8   | 2.8       | 0.7       | 52.8 – 62.9 |
| iTerm2          | 3.7.9                           | 17 | **60.4 ms** | 60.5   | 1.9       | 0.5       | 57.8 – 64.6 |
| btmux (Chrome)  | 0.0.222, Chrome 158.0.8127.88   | 19 | **63.1 ms** | 63.8   | 4.7       | 1.1       | 55.0 – 68.9 |
| Rex             | 0.1.0 (2147)                    | 16 | **65.3 ms** | 65.8   | 3.8       | 1.0       | 58.2 – 72.5 |
| btmux (app)     | 0.0.222                         | 23 | **65.5 ms** | 64.4   | 4.9       | 1.0       | 59.4 – 81.4 |
| Ghostty         | 1.4.0                           | 15 | **65.7 ms** | 67.0   | 3.9       | 1.0       | 58.0 – 70.1 |
| Terminal.app    | 2.15 (macOS 26.6.2)             | 14 | **68.1 ms** | 68.2   | 1.9       | 0.5       | 64.9 – 71.6 |
| cmux            | 0.65.2                          | 20 | **68.7 ms** | 68.7   | 2.5       | 0.6       | 61.6 – 72.2 |
| VS Code         | 1.147.0                         | 20 | **69.1 ms** | 69.8   | 4.9       | 1.1       | 61.4 – 76.6 |
| Orca            | 1.4.273                         | 19 | **69.4 ms** | 69.6   | 5.2       | 1.2       | 58.8 – 77.5 |
| Cursor          | 3.32.4                          | 18 | **71.0 ms** | 71.8   | 4.3       | 1.0       | 64.1 – 77.7 |
| herdr           | 0.1.18                          | 20 | **71.4 ms** | 71.5   | 2.4       | 0.5       | 65.4 – 75.3 |
| Zed             | 1.30.2                          | 22 | **82.1 ms** | 82.4   | 3.4       | 0.7       | 76.1 – 87.7 |

Standard errors are across key presses within one recording; they don't
capture how much a second recording would differ. Versions are those
installed at the time, each last updated before its recording. Per-event data
is in [`results/`](results/).

## Setup

- **Machine:** 16-inch MacBook Pro (M5 Pro), macOS 26.6.2, built-in display
  and keyboard. Refresh rate "ProMotion" (adaptive, up to 120 Hz); the
  rate during each key press wasn't measured.
- **Camera:** iPhone 16 Plus on a tripod, 240 fps slow motion, default export
  format.
- **Apps:** kitty, Ghostty, and Zed with default settings, VS Code and Cursor
  with only a theme set. Zed had no project open, so nothing was indexing and
  no language servers ran. Light themes throughout.
- **Shell:** zsh without a prompt theme or plugins. `a` was typed about twice
  a second at the prompt.
- **Session:** all on 2026-11-26 between 10:11 and 14:43.

## What the numbers include

Each latency runs from the start of the key's sound to the first camera frame
showing the character: keyboard, macOS, the app, compositing, and the display.
That makes them larger than an app's own processing time, and not comparable
with software-injected measurements such as Typometer. Compare rows with each
other, with two caveats: the display's actual refresh rate under ProMotion
wasn't measured and may differ between apps, and the audio onset depends on
how each key was struck.

## Takeaways

For these recordings on this machine:

- kitty (58.5 ms) and iTerm2 (60.4 ms) had the lowest means.
- btmux (app and Chrome), Rex, and Ghostty form one group at 63–66 ms. The
  gaps within it (at most 2.6 ms) are about as large as the change between
  repeat takes, so this data doesn't rank them.
- Terminal.app, cmux, VS Code, Orca, Cursor, and herdr follow at 68–71 ms.
- Zed had the highest mean in both takes (80.3 and 82.1 ms), 9–11 ms
  above herdr.
- Every standard deviation (2–5 ms) is under one 120 Hz refresh (8.3 ms).

## Repeat takes

| App | First take | Second take |
|---|---|---|
| cmux | 69.3 ± 0.6 ms (n=15) | 68.7 ± 0.6 ms (n=20) |
| herdr | 72.6 ± 0.6 ms (n=18) | 71.4 ± 0.5 ms (n=20) |
| Zed | 80.3 ± 0.9 ms (n=23) | 82.1 ± 0.7 ms (n=22) |

Takes were three to four and a half hours apart; ± is the standard error.
The means moved by 0.6, 1.2, and 1.8 ms. Three pairs aren't enough to say how
much takes vary in general. The main table uses the second takes.

## Audio/video sync

A calibration video from the same phone and export format shows a pencil tip
knocking on a table. In 7 knocks the tip touches the table 0.7–1.7 frames
(mean 1.2) after the sound starts, and a contact shows only in the next frame,
so sound and picture are in sync to within about one frame (4 ms).

## Notes

- **Slow-motion range.** Exported slow motion starts and ends at normal speed,
  where text follows a click within 2–3 frames instead of 13–18. Clicks on
  these ramps were left out: kitty 32; Cursor 47; iTerm2 40, 81, and 2274; Rex
  2211; VS Code 2789; btmux (app) 73 and 3118; btmux (Chrome) 56 and 2447;
  cmux (second take) 56 and 2487; herdr (second take) 52, 113, and 2655; Zed
  2987 (first take) and 44, 120, and 3131 (second take).
- **Moiré.** The phone picked up the screen's pixel grid, and the moiré
  flickers whenever a key press shakes the laptop. In Ghostty, kitty, and the
  first cmux take it swamped most characters, so each click was re-measured
  with a crop about three characters wide and set by hand. The second cmux
  take needed none. Other hand-set frames: herdr (first take) 1995 and 2377,
  Orca 2187 (a cursor blink was picked), Rex 218, 1858, and 1986, Terminal.app
  2071.
- **Search window.** About half the characters appear more than 16 frames
  (67 ms) after the click. A 16-frame window misses them and picks up other
  changes instead (for Zed's second take, a plausible-looking 53.9 ms), which
  is why the default `--max-frames` is 32.
- **Faint frames.** Many characters show faintly one frame early, a partial
  exposure, which doesn't count (see the README). The closest call is btmux
  (app) click 1719: counting it would make that event 77.2 ms instead of 81.4
  and the mean 0.2 ms lower.
- **Outlier.** Zed's first take, first click, took 95.8 ms, 10 ms above the
  rest. The contact sheet confirms it, so it was kept.
- **Not key presses.** Sounds that typed nothing: btmux (app) 644, Zed (second
  take) 1746 and 2411, Terminal.app 1298 and 1665 (`--skip`).

## Settings

Videos are `<label>-macbook-pro.MOV`. The detected text frames are in each
`results/<label>.json`.

```sh
./ktp.py measure btmux-app-macbook-pro.MOV    --crop 0,340,1080,100  --range 150:3100 --label btmux-app
./ktp.py measure btmux-chrome-macbook-pro.MOV --crop 0,395,1080,100  --range 100:2440 --label btmux-chrome
./ktp.py measure cmux-macbook-pro.MOV         --crop 0,600,1080,120  --range 150:2270 --label cmux         \
  --override 255=272 405=422 546=564 683=700 827=844 966=982 1102=1120 1251=1268 1395=1412 1539=1556 1679=1696 1818=1834 1954=1972 2091=2108 2230=2246
./ktp.py measure cmux-2-macbook-pro.MOV       --crop 0,598,1080,110  --range 100:2470 --label cmux-2
./ktp.py measure cursor-macbook-pro.MOV       --crop 0,440,1080,75   --range 150:2400 --label cursor
./ktp.py measure ghostty-macbook-pro.MOV      --crop 0,490,1080,130  --range 200:2200 --label ghostty      \
  --override 237=252 378=395 518=535 648=664 787=803 922=936 1057=1073 1186=1202 1327=1343 1468=1483 1595=1608 1733=1749 1869=1885 2006=2021 2141=2158
./ktp.py measure herdr-0.1.18-macbook-pro.MOV --crop 0,560,1080,70   --range 150:2640 --label herdr-0.1.18
./ktp.py measure herdr-app-macbook-pro.MOV    --crop 0,680,1080,100  --range 150:2420 --label herdr-app    --override 1995=2013 2377=2395
./ktp.py measure iterm2-macbook-pro.MOV       --crop 0,475,1080,75   --range 150:2250 --label iterm2
./ktp.py measure kitty-macbook-pro.MOV        --crop 0,495,1080,90   --range 100:2300 --label kitty        \
  --override 148=161 278=292 412=426 542=557 674=689 805=820 943=957 1070=1084 1202=1216 1335=1349 1466=1481 1594=1608 1728=1741 1847=1859 1983=1996 2119=2134 2245=2260
./ktp.py measure orca-macbook-pro.MOV         --crop 0,420,1080,90   --range 180:2830 --label orca         --override 2187=2205
./ktp.py measure rex-macbook-pro.MOV          --crop 0,545,1080,85   --range 160:2160 --label rex          --override 218=233 1858=1873 1986=2004
./ktp.py measure terminal-app-macbook-pro.MOV --crop 0,690,1080,120  --range 150:2120 --label terminal-app --override 2071=2088 --skip 1665
./ktp.py measure vscode-macbook-pro.MOV       --crop 300,270,780,170 --range 120:2770 --label vscode
./ktp.py measure zed-2-macbook-pro.MOV        --crop 0,508,1080,68   --range 200:3120 --label zed-2
./ktp.py measure zed-macbook-pro.MOV          --crop 0,165,1080,135  --range 100:2960 --label zed
```
