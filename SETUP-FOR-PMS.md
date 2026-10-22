# RFP Analyzer: setup and quick-start guide for PMs

This guide is for project managers who want to use the **RFP Analyzer** skill in Claude Code. You do not
need programming experience. Setup takes about 15 minutes and is done once.

**What you get:** point Claude at a folder of RFP documents, and it prepares the following for you to
review and edit:
- an executive summary
- a requirements list
- client clarification questions
- a man-day estimate
- risks and assumptions
- an approved Statement of Work (Word)

---

## Before you start

You need:
- **A company Claude account** (Team/Enterprise). If you don't have one, ask your manager or IT.
- **Access to the skill repository:** https://github.com/ayafaysalfaysal/rfp-analyzer-skill
  If the page says "404", ask the repository owner to give your GitHub account access.
- Permission to install software on your laptop (or help from IT).

---

## Step 1: Install Claude Code

Follow the official instructions at **https://code.claude.com/docs/en/setup**.

- **Windows:** open **PowerShell** (Start menu → type "PowerShell") and run the install command for
  Windows from that page.
- **Mac:** open **Terminal** and run the install command for macOS from that page.

When it finishes, type `claude` and press Enter. Sign in with your **company** Claude account when asked.
Type `/exit` to close it again.

> If you prefer working in VS Code, you can install the "Claude Code" extension from the VS Code
> marketplace instead. The rest of this guide works the same way.

## Step 2: Install Python

The skill uses Python to build the Excel and Word files.

- **Windows:** in PowerShell run:
  ```
  winget install -e --id Python.Python.3.12
  ```
  (or download it from https://www.python.org/downloads/ and **tick "Add python.exe to PATH"** during setup).
  Then **close and reopen PowerShell**.
- **Mac:** download it from https://www.python.org/downloads/ and run the installer.

Check that it worked: `python --version` (on Mac: `python3 --version`). You should see `Python 3.x`.

## Step 3: Download the skill

1. Open https://github.com/ayafaysalfaysal/rfp-analyzer-skill
2. Click the green **Code** button → **Download ZIP**, then unzip it.
3. Inside the unzipped folder, open `.claude` → `skills`. You will see a folder called **`rfp-analyzer`**.
   (On Windows, if you can't see `.claude`, enable *View → Show → Hidden items* in File Explorer.)
4. Copy the **`rfp-analyzer`** folder into your personal skills folder:
   - **Windows:** `C:\Users\<your-name>\.claude\skills\` (create the `skills` folder if it doesn't exist)
   - **Mac:** `/Users/<your-name>/.claude/skills/` (in Finder press **Cmd+Shift+G** and paste `~/.claude/skills`)

   The final location must be `...\.claude\skills\rfp-analyzer\SKILL.md`.

## Step 4: Install the skill's Python packages

- **Windows (PowerShell):**
  ```
  python -m pip install -r "$HOME\.claude\skills\rfp-analyzer\requirements.txt"
  ```
- **Mac (Terminal):**
  ```
  python3 -m pip install -r ~/.claude/skills/rfp-analyzer/requirements.txt
  ```

## Step 5: Add the company settings (recommended)

If your team lead shared a `config.yaml` file (company name, logo, team roles and so on), copy it into the
`rfp-analyzer` folder next to `SKILL.md`. Without it, the skill works with neutral defaults, but it will
not issue a final SOW until the company name is set.

To create one yourself, copy `config.example.yaml`, rename the copy to `config.yaml`, and change at least:
```yaml
company:
  name: "Your Company Name"
```

---

## Using it

1. Create a working folder for the bid, e.g. `Documents\Bids\CityPortal`.
2. Inside it, create a folder **`client-rfp`** and put **all** RFP documents in it: the main RFP, annexes,
   amendments, Q&A files and spreadsheets.
3. Open Claude Code **in the working folder**:
   - Windows: open the folder in File Explorer, type `powershell` in the address bar, press Enter, then type `claude`.
   - Mac: right-click the folder → *New Terminal at Folder*, then type `claude`.
   - VS Code: *File → Open Folder*, then open the Claude Code panel.
4. Type:
   ```
   /rfp-analyzer analyze ./client-rfp
   ```
   Claude reads every document and works through the analysis. It may ask permission to run commands;
   allow them. At the end it gives you a review summary.

The results appear in a new **`rfp-analysis`** folder:

| File | What it is |
|---|---|
| `01-executive-summary.md` | Plain-language summary of what the client wants |
| `02-requirements-matrix.xlsx` | Every requirement with its source |
| `03-client-clarifications-CLIENT-COPY.xlsx` | **Questions you can send to the client** |
| `03-client-clarifications.xlsx` | Internal version (includes internal notes; **do not send**) |
| `04-wbs-estimation.xlsx` | Work breakdown and man-day estimate (**internal**) |
| `05`, `06`, `08`, `11` (.md) | Risks and assumptions, scope recommendations, decision log, readiness check |
| `07-statement-of-work.docx` | Client SOW (only after you approve the baseline) |

### Everyday commands

| You want to… | Type |
|---|---|
| Continue where you left off | `/rfp-analyzer resume` |
| Record a client answer | `/rfp-analyzer answer Q-003 The client confirmed SSO via Azure AD` |
| Re-estimate after changes | `/rfp-analyzer estimate` |
| See the impact of a scope change | `/rfp-analyzer impact REQ-012 client wants SMS notifications too` |
| Check whether everything is consistent | `/rfp-analyzer validate` |
| Approve the scope and estimate | `/rfp-analyzer approve` |
| Produce the client SOW | `/rfp-analyzer sow` (or `sow --draft` before approval) |

You can also just ask in plain language, for example "what are the biggest risks?" or "make the
clarification questions shorter".

### Important rules

- **You are the approver.** Claude never approves on its own. It asks you, and records your name.
- **Review before sending.** Check the questions, estimate and SOW the same way you would check a colleague's draft.
- **Send only client-facing files**: the CLIENT COPY of the questions and the final SOW. Everything else is internal.
- **Confidentiality:** keep RFP folders on company storage only. Do not upload them or the
  `rfp-analysis` folder to personal cloud drives, public websites or GitHub.

---

## Updating the skill

When a new version is announced, download the ZIP again (Step 3) and replace the files inside your
`rfp-analyzer` folder. **Keep your `config.yaml`.** Then repeat Step 4.

## Troubleshooting

| Problem | What to do |
|---|---|
| `/rfp-analyzer` doesn't appear | Check the folder is exactly `.claude\skills\rfp-analyzer\SKILL.md`, then close and reopen Claude Code |
| "Python was not found" (Windows) | Re-install Python with "Add to PATH" ticked; close and reopen PowerShell. If it persists: Settings → Apps → Advanced app settings → App execution aliases → turn **off** the two "python" entries |
| "openpyxl/docx/yaml is required" | Repeat Step 4 |
| A scanned PDF can't be read | Claude will look at the pages as images; if quality is poor, ask the client for a text PDF |
| Old `.doc` / `.xls` files are "Unsupported" | Open and re-save them as `.docx` / `.xlsx` |
| "Baseline NOT approved" | Critical client questions are still open. Answer them, or approve while documenting the accepted risk |
| Word asks to "update fields" | Click **Yes** (fills in the table of contents and page numbers) |

Questions or suggestions? Contact the skill owner.
