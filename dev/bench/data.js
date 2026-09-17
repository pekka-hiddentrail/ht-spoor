window.BENCHMARK_DATA = {
  "lastUpdate": 1789624619638,
  "repoUrl": "https://github.com/pekka-hiddentrail/ht-spoor",
  "entries": {
    "Spoor exploration perf (small)": [
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "f64325f4bd2ce96812377e9408bf3f077892495b",
          "message": "Merge pull request #87 from pekka-hiddentrail/perf-bench\n\nAdd a deterministic exploration performance bench (§5.5)",
          "timestamp": "2026-09-15T21:59:12+03:00",
          "tree_id": "7aeb6c4cb6a7843e02e1b4a7615050e043c87487",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/f64325f4bd2ce96812377e9408bf3f077892495b"
        },
        "date": 1789499931181,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 118.047,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.03977,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 1.8068,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.13815,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 3.3013,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.06841,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 11.6332,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.10586,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 19.061,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.0426,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.2569,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.5626,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 29.1555,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.05676,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 14.0874,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 0.88007,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 29.7004,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.08784,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.531,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.01072,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.6465,
            "unit": "s"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "1db9da3722a326b31efec985d5623216fa45bf7f",
          "message": "Merge pull request #88 from pekka-hiddentrail/perf-seed-baseline\n\nAdd a baseline-seeding mode to the perf workflow (§5.5)",
          "timestamp": "2026-09-15T22:48:36+03:00",
          "tree_id": "a8589b32d11bda2ea59d57c522a33be9acc57e03",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/1db9da3722a326b31efec985d5623216fa45bf7f"
        },
        "date": 1789501875402,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 89.113,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.03569,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 0.962,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.132,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 2.8929,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.06171,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 11.228,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.1065,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 18.2021,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.05127,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.2711,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.55483,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 17.8881,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.05225,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 5.4511,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 0.87726,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 23.3036,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.09212,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.568,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.01073,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.4985,
            "unit": "s"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "249903e7b9911e67a7ea529291508300b6514049",
          "message": "Gate only reproducible perf counters + seed the baseline (§5.5) (#89)\n\n* Gate only reproducible perf counters; demote call counts to advisory (§5.5)\n\nA CI seeding run showed the assumption that per-operation call counts are\ndeterministic is false: the walk's replay/recovery loop reacts to the live\ntarget's runtime nondeterminism (Juice Shop is an SPA whose reset does not\nalways land identically), so reset/state_html/ax_nodes/probe/perform counts —\nand which replay-failure message a skip carries — vary run to run even for the\nidentical map. Two CI runs agreed on the structural and dedup counts but\ndisagreed on those.\n\nSo check_drift now gates only the reproducible counters (states, transitions,\nskipped, discovered, image_files, image_refs); the committed baseline holds only\nthose. Per-operation call counts and the skip-reason histogram are still\nreported (advisory lines in the run output, useful for triage) but never fail\nthe build. Corrects the §5.5 note accordingly.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>\n\n* Seed the committed juice-shop-small perf baseline (§5.5)\n\nCaptured on the CI runner via a workflow_dispatch update_baseline run and\ninspected: the six gated structural/dedup counters, matching both prior CI\nruns. With this committed the small-set drift gate is now live (fails on any\nchange to the crawl shape or dedup counts).\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>\n\n* Narrow perf gate to the pure graph shape; demote dedup counts to advisory (§5.5)\n\nA check-mode CI run proved image_refs wobbles run to run (151->152) while the\ngraph shape (states/transitions/skips/discovered) stays identical — the walk's\nreplay/recovery loop reacts to Juice Shop's SPA nondeterminism (an extra element\ncapture), which moves the capture counts without changing the map. So the dedup\ncounts join the per-op call counts and skip histogram as advisory-only signals;\nonly the four reproducible graph-shape counters gate against the committed\nbaseline. Re-seed the baseline to those four fields and reconcile the docstrings,\nROADMAP §5.5 and the workflow comment.\n\nCo-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>\n\n---------\n\nCo-authored-by: Claude Opus 4.8 <noreply@anthropic.com>",
          "timestamp": "2026-09-16T07:57:38+03:00",
          "tree_id": "af07c406d2e6fedc9f74e2e39f2ee8896c02dd4e",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/249903e7b9911e67a7ea529291508300b6514049"
        },
        "date": 1789534825831,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 85.133,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.03976,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 0.9862,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.12789,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 2.7799,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.06505,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 11.8579,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.10948,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 18.1959,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.04446,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.266,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.55624,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 17.9589,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.04382,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 4.4647,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 0.85249,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 19.8956,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.08533,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.5369,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.01076,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.4278,
            "unit": "s"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "0224f05041b6474a34e0b3a8f42f6ab4d61ea821",
          "message": "Add an event-anchored resource trace to the perf bench (§5.5) (#90)\n\nEvery timed transaction now also carries its start offset on the run's time axis\nand the resident memory (this process + children, via psutil, so Chromium counts)\nsampled just before and after the call — bracketing each browser round-trip so a\nmemory step attributes to the operation that caused it. RSS is read outside the\nperf_counter window, so sampling never inflates the reported per-op duration.\n\nThe trace is a within-run diagnostic: like the walk-dependent call counts it is\nnondeterministic run to run, so it is never gated. It is emitted as a per-run\nJSON timeline artifact (ordered t_start/duration/op/detail/rss_before/rss_after\nrows, ready to stretch onto a timeline), and its one scalar reduction — peak RSS —\nrides the advisory dashboard as a smaller-is-better trend line beside the timing\nrows. psutil is a dev/bench-only dependency; when it is absent the readings are 0\nand the trace degrades to timing-only (no flatline row is charted).\n\nRendering the trace to a matplotlib timeline PNG on gh-pages is the next slice;\nthis lands the collection and the artifact it will consume.\n\nCo-authored-by: Claude Opus 4.8 <noreply@anthropic.com>",
          "timestamp": "2026-09-16T09:08:27+03:00",
          "tree_id": "f26f71a9f828b0f87d09b22b283c2a16789e1a58",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/0224f05041b6474a34e0b3a8f42f6ab4d61ea821"
        },
        "date": 1789539077175,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 92.301,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.04408,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 1.1248,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.13171,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 3.0153,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.06197,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 11.9996,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.1076,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 18.1608,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.06239,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.2933,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.55647,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 17.9791,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.05369,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 5.3832,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 0.87312,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 20.0864,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.09411,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.5655,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.01073,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.4303,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / peak RSS",
            "value": 3735.9,
            "unit": "MB"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "871b317972393d45574057b769c59e4d585486ba",
          "message": "Merge pull request #92 from pekka-hiddentrail/exploration-settling-announcements\n\nSettle also waits out urgent live-region announcements (§2e, 7f)",
          "timestamp": "2026-09-16T11:35:29+03:00",
          "tree_id": "cdeb6253c877353e4b8be65cc43bb8c8ff095c06",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/871b317972393d45574057b769c59e4d585486ba"
        },
        "date": 1789548003898,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 200.365,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.0284,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 1.33,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.09519,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 2.3739,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.05233,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 8.4694,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.08139,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 13.3241,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.03077,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.1668,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.55956,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 29.212,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.0332,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 8.8058,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 5.92434,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 124.574,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.07231,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.4359,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.00789,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.3488,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / peak RSS",
            "value": 4969.7,
            "unit": "MB"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "2fa95b80accbed9c77666f13eb9f4fc71a14c866",
          "message": "Merge pull request #91 from pekka-hiddentrail/perf-trace-report\n\nRender the perf resource trace as an interactive HTML report (§5.5)",
          "timestamp": "2026-09-16T11:54:28+03:00",
          "tree_id": "c3738d8d168cc5f61f9fe39bef4d8fde9010935a",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/2fa95b80accbed9c77666f13eb9f4fc71a14c866"
        },
        "date": 1789549164219,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 214.82,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.04013,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 1.9325,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.11437,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 2.7196,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.06396,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 10.7082,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.11826,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 17.0089,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.04364,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.2488,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.57922,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 32.2825,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.04711,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 11.9888,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 5.986,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 126.2121,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.0844,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.5475,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.00968,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.4336,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / peak RSS",
            "value": 5299.7,
            "unit": "MB"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "18800c0ce3feebda7fab238fde6edd626f016676",
          "message": "Merge pull request #93 from pekka-hiddentrail/roadmap-second-round-exploration\n\nDesign notes: §2e v2 exploration — interactive second round + anchored resume",
          "timestamp": "2026-09-16T13:48:26+03:00",
          "tree_id": "b8b3b9f07bd65d73a6f80b8c5c92b8d8bc35a865",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/18800c0ce3feebda7fab238fde6edd626f016676"
        },
        "date": 1789555986393,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 206.23,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.03034,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 1.5978,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.10139,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 2.4305,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.05642,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 9.2217,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.08644,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 14.3451,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.03356,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.2091,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.56073,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 31.6298,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.03548,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 9.8691,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 5.92567,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 124.6125,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.0746,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.4728,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.00862,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.3761,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / peak RSS",
            "value": 5284.3,
            "unit": "MB"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "7c752d79e30d38bd6fed0fac808ac045574c7c23",
          "message": "Merge pull request #94 from pekka-hiddentrail/exploration-anchor-selector\n\nResolve a state-selector to one anchor state (§2e resume, slice 1)",
          "timestamp": "2026-09-16T14:04:40+03:00",
          "tree_id": "4cbf898060e1c7ca9b0b0d68887c3c24deb79b4e",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/7c752d79e30d38bd6fed0fac808ac045574c7c23"
        },
        "date": 1789556974632,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 209.85,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.03167,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 1.5331,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.1009,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 2.4174,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.05643,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 10.3625,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.09238,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 15.5385,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.03406,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.2441,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.55945,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 31.6086,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.0401,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 10.4965,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 5.92142,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 124.7036,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.07857,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.4748,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.0088,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.3945,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / peak RSS",
            "value": 5345.2,
            "unit": "MB"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "bfc9e37b3c58c59f701f91ebb573b47e7384e1b5",
          "message": "Merge pull request #95 from pekka-hiddentrail/exploration-graph-candidates\n\nBuild anchor candidates from an exploration graph (§2e resume, slice 2)",
          "timestamp": "2026-09-16T15:59:55+03:00",
          "tree_id": "146ca5ef68b12c8610bb320e93800a11b8a4743f",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/bfc9e37b3c58c59f701f91ebb573b47e7384e1b5"
        },
        "date": 1789563891268,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 218.82,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.0369,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 1.9789,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.11371,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 2.7561,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.06697,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 11.2967,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.11808,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 18.1896,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.04723,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.2725,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.58455,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 32.4762,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.05029,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 12.6618,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 5.98763,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 126.2053,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.09534,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.5625,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.00969,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.4178,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / peak RSS",
            "value": 5348.9,
            "unit": "MB"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ba5401d9a067718e76cdd2a2e1e5e47aa3b4d4e8",
          "message": "Merge pull request #97 from pekka-hiddentrail/exploration-persisted-map\n\nLoad a persisted exploration map back into a graph (§2e resume, slice 3)",
          "timestamp": "2026-09-16T16:16:04+03:00",
          "tree_id": "08c739e28fa0b56c5bd9378a5a3e25978790e65b",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/ba5401d9a067718e76cdd2a2e1e5e47aa3b4d4e8"
        },
        "date": 1789564849072,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 220.857,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.03804,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 1.9183,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.12317,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 2.9479,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.06406,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 11.1736,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.11102,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 17.59,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.04248,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.2658,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.57286,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 32.044,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.05042,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 12.3875,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 5.98367,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 126.3981,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.08204,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.5139,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.01048,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.4658,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / peak RSS",
            "value": 5370.6,
            "unit": "MB"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "483b13f8ca544b3195c3004dda4cac154f547523",
          "message": "Merge pull request #98 from pekka-hiddentrail/exploration-resume-traversal\n\nResume exploration from a mapped anchor (§2e resume, slice 4)",
          "timestamp": "2026-09-17T00:05:01+03:00",
          "tree_id": "622cfca9ec19e18f988b5cdadea057f9ca60bf59",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/483b13f8ca544b3195c3004dda4cac154f547523"
        },
        "date": 1789592995268,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 228.353,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.03928,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 2.1749,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.12229,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 2.9029,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.06504,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 10.7294,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.1093,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 17.9056,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.04092,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.2605,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.57303,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 32.1794,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.04992,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 12.4757,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 5.99841,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 132.4488,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.0845,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.5152,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.01039,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.4639,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / peak RSS",
            "value": 5299.2,
            "unit": "MB"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "ec34fc81a64ef345deaf5b8a75960d1cd3040504",
          "message": "Merge pull request #99 from pekka-hiddentrail/testgen-writer-live-run\n\nWrite the generated regression suite to disk and run it (§2g, slice 2g-ii)",
          "timestamp": "2026-09-17T01:03:52+03:00",
          "tree_id": "d76978d5c051d2c0acda24500b3254ea35ba01cc",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/ec34fc81a64ef345deaf5b8a75960d1cd3040504"
        },
        "date": 1789596516831,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 220.977,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.03938,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 2.0485,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.12438,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 2.9917,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.06184,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 11.1122,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.10957,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 17.756,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.04966,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.2656,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.57234,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 32.0672,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.05081,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 12.4023,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 5.97663,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 126.1336,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.0902,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.5559,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.01035,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.4473,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / peak RSS",
            "value": 5244.5,
            "unit": "MB"
          }
        ]
      },
      {
        "commit": {
          "author": {
            "email": "103989476+pekka-hiddentrail@users.noreply.github.com",
            "name": "pekka-hiddentrail",
            "username": "pekka-hiddentrail"
          },
          "committer": {
            "email": "noreply@github.com",
            "name": "GitHub",
            "username": "web-flow"
          },
          "distinct": true,
          "id": "73afd4496fcf45c63e4f9ee73e871c49d222f026",
          "message": "Merge pull request #100 from pekka-hiddentrail/wiki-subfolder-layout\n\nGroup wiki state and transition pages into subfolders (§2e, slice 6g)",
          "timestamp": "2026-09-17T08:52:10+03:00",
          "tree_id": "0a70da5819d9c72411db8b11d1d060e3ef4d706f",
          "url": "https://github.com/pekka-hiddentrail/ht-spoor/commit/73afd4496fcf45c63e4f9ee73e871c49d222f026"
        },
        "date": 1789624618781,
        "tool": "customSmallerIsBetter",
        "benches": [
          {
            "name": "juice-shop-small / total elapsed",
            "value": 205.363,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes median",
            "value": 0.02721,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / ax_nodes total",
            "value": 1.4212,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals median",
            "value": 0.10023,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / capture_signals total",
            "value": 2.3903,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url median",
            "value": 0.00001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / current_url total",
            "value": 0.0001,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box median",
            "value": 0.05451,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_box total",
            "value": 9.2113,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot median",
            "value": 0.09188,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / element_screenshot total",
            "value": 14.282,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot median",
            "value": 0.04521,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / opened_screenshot total",
            "value": 0.2315,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform median",
            "value": 0.56391,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / perform total",
            "value": 31.2441,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe median",
            "value": 0.03499,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / probe total",
            "value": 9.5669,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset median",
            "value": 5.9359,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / reset total",
            "value": 125.1622,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot median",
            "value": 0.07759,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / screenshot total",
            "value": 0.4514,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html median",
            "value": 0.00843,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / state_html total",
            "value": 0.3601,
            "unit": "s"
          },
          {
            "name": "juice-shop-small / peak RSS",
            "value": 5385.8,
            "unit": "MB"
          }
        ]
      }
    ]
  }
}