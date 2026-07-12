# Always-on dashboard runbook

## What this is

The primary airline dashboard is a static website hosted free by GitHub Pages:

- Dashboard: <https://battina1999.github.io/airline-data-platform/>
- dbt catalog and lineage: <https://battina1999.github.io/airline-data-platform/lineage/>
- Optional Streamlit version: <https://airline-ops-battina.streamlit.app/>

“Static” means the browser downloads HTML, CSS, JavaScript, and a small JSON data file. There is no server to start when someone visits, so the GitHub Pages dashboard does not go to sleep.

The Streamlit Community Cloud app is still available for the Python version of the experience. On the free service, Streamlit normally sleeps after 12 hours without visitors. That sleeping screen is a hosting rule, not a broken dashboard, which is why Streamlit is now optional rather than the main link.

## How the pieces fit together

```text
dashboards/public_data/*.parquet (committed aggregate data)
                     |
                     v
docs/dashboard/scripts/build_data.py
                     |
                     v
data/dashboard-data.json + index.html + app.js + styles.css
                     |
                     v
GitHub Pages root

dbt docs ------------------------------> GitHub Pages /lineage/
```

The browser never reads the Parquet files directly. During deployment, `build_data.py` converts the committed Parquet marts into the JSON used by `app.js`. No database, API token, secret, or running Python process is needed after deployment.

## Automatic deployment

Every push to `main` starts `.github/workflows/docs.yml`, named **Publish always-on dashboard and lineage**. It:

1. Checks out the repository and installs the CI dependencies.
2. Builds the sample warehouse and generates the static dbt documentation.
3. Generates `dashboard-data.json` from the committed Parquet extract.
4. Places the dashboard at the Pages root and dbt documentation under `/lineage/`.
5. Validates the HTML, JavaScript, JSON, and lineage files.
6. Publishes the Pages artifact and checks both public URLs.

No manual deployment is needed after a successful push.

## Preview locally

Run these commands from the repository root:

```bash
python -m pip install -r requirements-ci.txt
python docs/dashboard/scripts/build_data.py
python -m http.server 8000 --directory docs/dashboard
```

Then open <http://localhost:8000/>. Stop the preview with `Ctrl+C`.

To rebuild the committed public data before previewing:

```bash
python -m orchestration.run_pipeline
python scripts/export_public_extract.py
python docs/dashboard/scripts/build_data.py
```

Review the Parquet and JSON changes before committing them.

## Quick failure checks

| Symptom | First check | Likely fix |
| --- | --- | --- |
| GitHub Pages shows 404 | Repository **Actions** → **Publish always-on dashboard and lineage** | Fix the failed workflow step, then rerun it or push the correction. |
| Page opens but says data could not be loaded | Browser request for `data/dashboard-data.json` and the workflow's JSON validation | Run `python docs/dashboard/scripts/build_data.py`, then `python -m json.tool docs/dashboard/data/dashboard-data.json`. |
| `/lineage/` is missing | The workflow's **Generate dbt docs** step | Fix the dbt build/docs error; the dashboard itself can still remain static. |
| Numbers look old | `dashboards/public_data/_provenance.txt` and committed Parquet files | Refresh the public extract, regenerate JSON, review, and commit. |
| Streamlit shows `Zzzz` | Nothing is wrong with GitHub Pages | Use the Pages dashboard; wake Streamlit only when its optional version is wanted. |

For maintainers, treat `.github/workflows/docs.yml` as the deployment source of truth and `dashboards/public_data/` as the published data source. Do not hand-edit `dashboard-data.json`; regenerate it with `build_data.py`.
