# CareerHub Phase 3

## Fixed
- Fixed profile-save 413 errors caused by the request-wide upload limit.
- Profile multipart requests now support a 12 MB total request by default.
- Individual limits remain: resume 4 MB, photo 2 MB.

## Candidate experience
- ATS-friendly Resume Builder.
- PDF resume download.
- Application Timeline with status history.
- Candidate dashboard shortcut to Resume Builder.
- Application list links to Timeline.
- Natural-language job search understands common intent such as `python developer fresher delhi`, `react developer remote`, `java developer 5 lpa`, and `python developer 2 years`.

## Recruiter ATS
- Candidate search/filter by name, skills, education and status.
- Private recruiter notes per application.
- Timeline notes when application status changes.
- Status history stored in the database.
- Initial Applied and candidate Withdrawn states are recorded.

## Database / One-click
- Added migration `0005_phase3`.
- Setup uses Flask-Migrate for schema creation.
- Start script checks migrations before starting.
- Legacy auto-created local databases receive a safe Phase-3 column repair.
