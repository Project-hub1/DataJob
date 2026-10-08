from pathlib import Path


def test_phase4_ats_code_contract():
    model = Path('app/models/application.py').read_text(encoding='utf-8')
    routes = Path('app/recruiter/routes.py').read_text(encoding='utf-8')
    assert 'recruiter_rating' in model
    assert 'recruiter_tags' in model
    assert "'/jobs/<int:job_id>/pipeline'" in routes
    assert "'/applications/<int:application_id>'" in routes
    assert "'/applications/<int:application_id>/bulk-status'" in routes


def test_phase4_migration_revision():
    text = Path('migrations/versions/0006_phase4_ats_pipeline.py').read_text(encoding='utf-8')
    assert 'revision = "0006_phase4"' in text
    assert 'down_revision = "0005_phase3"' in text
