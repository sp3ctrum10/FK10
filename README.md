# Job Application Automation

This repository contains a small Python utility that automates the repetitive
steps of preparing job applications. Provide a structured configuration file
with candidate details, job information, and custom questions and the script
generates:

- A Markdown summary containing all of the information you typically need to
  paste into an applicant tracking system (ATS).
- A JSON manifest enumerating the answers and attachments you intend to use.

## Getting Started

1. Ensure you have Python 3.8 or later available on your system.
2. (Optional) Install PyYAML if you would like to use YAML configuration files:
   `pip install pyyaml`
3. Run the script using one of the provided examples:

   ```bash
   python job_filler.py --config examples/sample_application.json --output ./out
   ```

4. Inspect the generated Markdown file and copy the content into the target
   application form. The JSON manifest can be used to track the submission in a
   spreadsheet or job tracker.

The `examples/` directory includes a starter configuration that demonstrates
how to compose templated responses, while the `resources/` directory contains
sample documents referenced by that configuration.
