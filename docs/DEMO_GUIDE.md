# Demonstrating Climate Lens in your interview

## Prepare before the call

1. Open the final app and run Hyderabad for 1990–2025 once, so it is cached.
2. Open the GitHub README and the local code in your editor.
3. Keep `backend/climate.py`, `backend/main.py`, and `frontend/App.tsx` ready.
4. Run the tests before the interview. Have a second terminal ready for changes.
5. Keep your microphone and screen recording ready if you are making the optional demo video.
6. Use the complete app for submission; the labeled fixed-location UI preview is for reviewing appearance and interactions.

## A four-minute screen demonstration

| Time | What to show | What to explain |
|---|---|---|
| 0:00–0:25 | Dashboard and city/year controls | “This app analyzes historical heatwave trends for a selected location using a React frontend, Python API, and a NoSQL database.” |
| 0:25–1:00 | Threshold card and Methodology tab | “A heatwave is at least three consecutive days above a fixed location-specific 95th-percentile threshold. The baseline is 1991–2020 and stays the same when I change the displayed period.” |
| 1:00–1:45 | Days, Frequency, Intensity, and Duration chart tabs | “These are different indicators. The rolling average smooths short-term variation; the linear fit describes direction. Neither proves causation.” |
| 1:45–2:15 | Evidence quality and Annual data | “Missing or invalid days break runs. Years below 95% coverage are excluded from regression and appear as gaps. Zero events and undefined intensity are different.” |
| 2:15–2:45 | Event log and a repeated Run analysis | “The log exposes the events behind the aggregates. Repeating a query reads the saved analysis from the database, which avoids another weather API call.” |
| 2:45–3:15 | Change to New Delhi or a different year range | “The same data model and definition apply to another location. Region-specific thresholds are recalculated from that location's fixed baseline.” |
| 3:15–3:40 | Export CSV, then API docs | “Exports contain the annual results and method metadata. FastAPI exposes the validated request/response schema.” |
| 3:40–4:00 | README AI disclosure and limitations | “I used AI substantially to assist implementation and testing. I can walk through the logic and explain where the assumptions need refinement.” |

Do not read every sentence. Show one result, explain why it matters, and move on.

## Explain the Hyderabad result honestly

In the verified 13 October 2026 run, the app reported **61 events**, **465 heatwave days**, a **39.3°C threshold**, and **100% daily coverage** for 1990–2025. Under this particular definition, the first/last five-year comparison showed a decrease. The full-period linear heatwave-day slope was approximately −0.26 days per decade with very low R².

Say: “The chosen periods and indicator do not imply that every heat metric must increase. The app displays the calculated result and its weak linear fit. A seasonal threshold, another location, or a different window could produce a different pattern. This analysis does not attribute changes to a cause.”

Use the current displayed numbers if the data source has changed. Do not claim statistical significance.

## A simple live change to practice

Change the minimum run length from 3 to 5 using **Heatwave definition**. Run the analysis again. Some short events should disappear, while the temperature baseline and raw weather remain the same.

To change the backend default, edit `min_duration` in `backend/models.py`. To change the initial UI value, edit `min_duration` in `frontend/App.tsx`. The pure `detect_heatwaves` function accepts the run length as an argument; the cache key includes that setting, so results for different definitions do not collide.

Practice a second change: add a “Mean temperature” chart tab using the existing `mean_tmax_c` annual field and its regression. Explain that this is a separate temperature indicator, not heatwave intensity.

## Common questions and short answers

**Why keep the baseline fixed?**
A changing baseline changes the comparison yardstick. A fixed baseline lets us compare the selected decades using the same threshold.

**What happens when a day is missing?**
The run breaks. I do not invent an observation. I show coverage and exclude low-coverage years from trend fitting.

**What happens to an event crossing 31 December?**
It stays one event, counted in its onset year. Its heatwave days are split across their actual calendar years.

**Why MongoDB?**
Raw weather and nested analysis results fit document storage well. MongoDB provides durable cloud storage, TTL indexes for cache expiry, and atomic counters for rate limiting. TinyDB supports an easy local demonstration without cloud credentials.

**How do you stop arbitrary external requests?**
The server fixes the API hosts in code. A caller supplies bounded coordinates and years, not a URL. Timeouts, response limits, no redirects, and bounded retries constrain upstream work.

**Why might the comparison and fitted slope tell different stories?**
The comparison uses only two endpoint windows. Regression uses all reliable years. A variable series can have a large endpoint difference and a weak overall linear slope.

**What did AI do?**
“I used ChatGPT/Codex substantially for architecture, implementation, tests, documentation, and deployment assistance. I disclose that in the README. I am reviewing the code and practicing explanations and changes.” Only claim independent understanding after you have practiced it.

**What would you improve first?**
A seasonally varying percentile and an explicit uncertainty analysis, followed by spatial averaging and distributed ingestion controls.

## Submission fields

- Repository: `https://github.com/vinilgarrepelli/climate-hazard-analyzer`
- Deployed URL: use the final, externally accessible complete application URL.
- AI tools: OpenAI ChatGPT/Codex; substantial assistance for code, testing, documentation, and deployment.
- Optional video: record the four-minute flow above, upload it to your own Loom/Drive account, and use a reviewer-accessible link.

Check the submission form deadline and submit once. Do not upload the confidential assignment brief publicly.
