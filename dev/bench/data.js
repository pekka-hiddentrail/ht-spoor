window.BENCHMARK_DATA = {
  "lastUpdate": 1789501875909,
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
      }
    ]
  }
}