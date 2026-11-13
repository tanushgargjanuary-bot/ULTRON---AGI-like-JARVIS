---
name: documents
description: Make a real .docx, .xlsx, .pptx or .pdf with the libraries already installed, then prove the file opens and says what it should.
---

# Documents

The machine has python-docx, python-pptx, openpyxl, reportlab, pypdf and
PyMuPDF. Use them to produce a file the owner can open, not a wall of text in
chat.

## Rules

- **One file, one purpose.** A report is a .docx. Figures are a .xlsx. A deck
  is a .pptx. A finished read-only copy is a .pdf.
- **Save next to the work**, then attach it. A path the owner cannot click is
  not a deliverable.
- **Read it back.** Open the file with the same library and check the title,
  the sheet names, the slide count or the page count. A saved file that is
  empty is a silent failure.
- **Never invent numbers.** If a figure is not in the source, leave it out or
  label it an example.
- **No macros, no embedded scripts, no external links** in a document that
  leaves this machine.

## Shape that reads well

- A title, a date, and one sentence saying what the document is for.
- Short sections with headings a reader can scan.
- Tables for comparisons. Prose for reasoning. Do not mix them in one cell.
- A source line for every number that came from outside.

## PowerPoint

One idea per slide, six lines at most, no paragraph. A deck is a set of claims,
not a document split into pages.

## Spreadsheet

- Header row frozen, one table per sheet, real column types.
- Formulas over pasted values where the owner may change an input.
- A second sheet with the source and the date.

## PDF

Generate from the source format where possible. Use reportlab for a created
document, PyMuPDF for reading and page work. Check the page count and that the
text is selectable - a scan of your own text is a downgrade.
