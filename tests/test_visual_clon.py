"""Tests for Visual Clon service, backup and models."""
import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_fake_eve_folder(base: Path, char_ids=('111', '222', '333')) -> Path:
    """Create a fake EVE settings_Default folder with dummy .dat files."""
    base.mkdir(parents=True, exist_ok=True)
    for cid in char_ids:
        f = base / f"core_char_{cid}.dat"
        f.write_bytes(b'\x00' * 1024)
    (base / 'core_user_9999.dat').write_bytes(b'\x00' * 512)
    return base


# ── Model tests ────────────────────────────────────────────────────────────────

class TestEveCharProfile(unittest.TestCase):

    def test_display_name_with_name(self):
        from core.visual_clon_models import EveCharProfile
        p = EveCharProfile(char_id='12345', file_path=Path('/x'), file_size=0,
                           char_name='Test Pilot')
        self.assertEqual(p.display_name, 'Test Pilot (12345)')

    def test_display_name_without_name(self):
        from core.visual_clon_models import EveCharProfile
        p = EveCharProfile(char_id='99999', file_path=Path('/x'), file_size=0)
        self.assertEqual(p.display_name, 'Personaje 99999')

    def test_eve_settings_folder_valid(self):
        from core.visual_clon_models import EveCharProfile, EveSettingsFolder
        folder = EveSettingsFolder(path=Path('/tmp'))
        self.assertFalse(folder.is_valid())

        folder.char_profiles.append(
            EveCharProfile(char_id='1', file_path=Path('/tmp'), file_size=0)
        )
        with patch.object(Path, 'is_dir', return_value=True):
            self.assertTrue(folder.is_valid())

    def test_backup_record_to_dict(self):
        from core.visual_clon_models import BackupRecord
        now = datetime(2026, 1, 15, 12, 30, 0)
        rec = BackupRecord(
            backup_dir=Path('/backups/foo'),
            timestamp=now,
            source_char_id='111',
            target_char_id='222',
            original_files=[Path('/settings/core_char_222.dat')],
        )
        d = rec.to_dict()
        self.assertEqual(d['source_char_id'], '111')
        self.assertEqual(d['target_char_id'], '222')
        self.assertIn('backup_dir', d)
        self.assertIn('original_files', d)
        self.assertEqual(d['timestamp'], '2026-01-15T12:30:00')


# ── Service tests ──────────────────────────────────────────────────────────────

class TestScanSettingsFolder(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_scan_finds_char_files(self):
        from core.visual_clon_service import scan_settings_folder
        _make_fake_eve_folder(self.tmp, char_ids=['111', '222'])
        folder = scan_settings_folder(self.tmp)
        self.assertEqual(len(folder.char_profiles), 2)
        ids = {p.char_id for p in folder.char_profiles}
        self.assertEqual(ids, {'111', '222'})

    def test_scan_finds_user_profiles(self):
        from core.visual_clon_service import scan_settings_folder
        _make_fake_eve_folder(self.tmp, char_ids=['111'])
        folder = scan_settings_folder(self.tmp)
        self.assertIn('9999', folder.user_profile_ids)

    def test_scan_sorts_by_char_id(self):
        from core.visual_clon_service import scan_settings_folder
        _make_fake_eve_folder(self.tmp, char_ids=['333', '111', '222'])
        folder = scan_settings_folder(self.tmp)
        ids = [p.char_id for p in folder.char_profiles]
        self.assertEqual(ids, sorted(ids))

    def test_scan_empty_folder(self):
        from core.visual_clon_service import scan_settings_folder
        folder = scan_settings_folder(self.tmp)
        self.assertEqual(len(folder.char_profiles), 0)
        self.assertFalse(folder.is_valid())

    def test_scan_ignores_non_dat_files(self):
        from core.visual_clon_service import scan_settings_folder
        (self.tmp / 'prefs.ini').write_text('[prefs]')
        (self.tmp / 'cache.bin').write_bytes(b'\x00')
        folder = scan_settings_folder(self.tmp)
        self.assertEqual(len(folder.char_profiles), 0)


class TestValidateSettingsFolder(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_valid_folder(self):
        from core.visual_clon_service import validate_settings_folder
        _make_fake_eve_folder(self.tmp, char_ids=['111'])
        ok, msg = validate_settings_folder(self.tmp)
        self.assertTrue(ok)
        self.assertIn('1', msg)

    def test_invalid_no_dat_files(self):
        from core.visual_clon_service import validate_settings_folder
        ok, msg = validate_settings_folder(self.tmp)
        self.assertFalse(ok)
        self.assertIn('core_char_', msg)

    def test_invalid_nonexistent(self):
        from core.visual_clon_service import validate_settings_folder
        ok, msg = validate_settings_folder(Path('/nonexistent/path/xyz'))
        self.assertFalse(ok)


class TestBuildCopyPlan(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        _make_fake_eve_folder(self.tmp, char_ids=['111', '222', '333'])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _profile(self, cid):
        from core.visual_clon_models import EveCharProfile
        return EveCharProfile(
            char_id=cid,
            file_path=self.tmp / f"core_char_{cid}.dat",
            file_size=1024,
        )

    def test_plan_excludes_source_from_targets(self):
        from core.visual_clon_service import build_copy_plan
        src = self._profile('111')
        targets = [self._profile('111'), self._profile('222')]
        plan = build_copy_plan(src, targets, dry_run=True)
        self.assertNotIn('111', [t.char_id for t in plan.targets])

    def test_plan_dry_run_flag(self):
        from core.visual_clon_service import build_copy_plan
        src = self._profile('111')
        plan = build_copy_plan(src, [self._profile('222')], dry_run=True)
        self.assertTrue(plan.dry_run)

    def test_plan_has_files(self):
        from core.visual_clon_service import build_copy_plan
        src = self._profile('111')
        plan = build_copy_plan(src, [self._profile('222')], dry_run=True)
        self.assertTrue(len(plan.files_to_copy) > 0)


class TestExecuteCloneDryRun(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        _make_fake_eve_folder(self.tmp, char_ids=['111', '222'])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _profile(self, cid):
        from core.visual_clon_models import EveCharProfile
        return EveCharProfile(
            char_id=cid,
            file_path=self.tmp / f"core_char_{cid}.dat",
            file_size=1024,
        )

    def test_dry_run_copies_nothing(self):
        from core.visual_clon_service import build_copy_plan, execute_clone
        src = self._profile('111')
        plan = build_copy_plan(src, [self._profile('222')], dry_run=True)
        result = execute_clone(plan)
        self.assertTrue(result.dry_run)
        self.assertEqual(len(result.files_copied), 0)
        self.assertEqual(len(result.backups), 0)

    def test_dry_run_success(self):
        from core.visual_clon_service import build_copy_plan, execute_clone
        src = self._profile('111')
        plan = build_copy_plan(src, [self._profile('222')], dry_run=True)
        result = execute_clone(plan)
        self.assertTrue(result.success)
        self.assertEqual(len(result.errors), 0)

    def test_dry_run_log_contains_simulacion(self):
        from core.visual_clon_service import build_copy_plan, execute_clone
        src = self._profile('111')
        plan = build_copy_plan(src, [self._profile('222')], dry_run=True)
        result = execute_clone(plan)
        combined = ' '.join(result.log_lines)
        self.assertIn('SIMULACI', combined)

    def test_no_targets_returns_error(self):
        from core.visual_clon_service import build_copy_plan, execute_clone
        src = self._profile('111')
        plan = build_copy_plan(src, [], dry_run=True)
        result = execute_clone(plan)
        self.assertFalse(result.success)
        self.assertTrue(len(result.errors) > 0)


class TestExecuteCloneApply(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.backup_tmp = Path(tempfile.mkdtemp())
        _make_fake_eve_folder(self.tmp, char_ids=['111', '222'])

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.backup_tmp, ignore_errors=True)

    def _profile(self, cid):
        from core.visual_clon_models import EveCharProfile
        return EveCharProfile(
            char_id=cid,
            file_path=self.tmp / f"core_char_{cid}.dat",
            file_size=1024,
        )

    def test_apply_creates_backup_before_copy(self):
        from core.visual_clon_service import build_copy_plan, execute_clone
        import core.visual_clon_backup as bk_mod

        with patch.object(bk_mod, 'get_backup_root', return_value=self.backup_tmp):
            src = self._profile('111')
            plan = build_copy_plan(src, [self._profile('222')], dry_run=False)
            result = execute_clone(plan)

        self.assertTrue(result.success)
        self.assertEqual(len(result.backups), 1)

    def test_apply_copies_file(self):
        from core.visual_clon_service import build_copy_plan, execute_clone
        import core.visual_clon_backup as bk_mod

        src_content = b'\xDE\xAD\xBE\xEF' * 256
        (self.tmp / 'core_char_111.dat').write_bytes(src_content)

        with patch.object(bk_mod, 'get_backup_root', return_value=self.backup_tmp):
            src = self._profile('111')
            plan = build_copy_plan(src, [self._profile('222')], dry_run=False)
            result = execute_clone(plan)

        dst = self.tmp / 'core_char_222.dat'
        self.assertEqual(dst.read_bytes(), src_content)
        self.assertEqual(len(result.files_copied), 1)

    def test_apply_does_not_copy_to_self(self):
        from core.visual_clon_service import build_copy_plan, execute_clone
        import core.visual_clon_backup as bk_mod

        with patch.object(bk_mod, 'get_backup_root', return_value=self.backup_tmp):
            src = self._profile('111')
            plan = build_copy_plan(src, [src], dry_run=False)
            result = execute_clone(plan)

        self.assertEqual(len(result.files_copied), 0)


# ── Backup tests ───────────────────────────────────────────────────────────────

class TestBackup(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.backup_root = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self.backup_root, ignore_errors=True)

    def test_create_backup_copies_file(self):
        import core.visual_clon_backup as bk_mod
        from core.visual_clon_backup import create_backup

        src_file = self.tmp / 'core_char_222.dat'
        src_file.write_bytes(b'\xAB' * 100)

        with patch.object(bk_mod, 'get_backup_root', return_value=self.backup_root):
            record = create_backup('111', '222', [src_file])

        self.assertEqual(len(record.original_files), 1)
        backed_up = record.backup_dir / 'core_char_222.dat'
        self.assertTrue(backed_up.exists())
        self.assertEqual(backed_up.read_bytes(), b'\xAB' * 100)

    def test_create_backup_writes_manifest(self):
        import core.visual_clon_backup as bk_mod
        from core.visual_clon_backup import create_backup

        src_file = self.tmp / 'core_char_222.dat'
        src_file.write_bytes(b'\x00' * 10)

        with patch.object(bk_mod, 'get_backup_root', return_value=self.backup_root):
            record = create_backup('111', '222', [src_file])

        manifest = record.backup_dir / 'backup_manifest.json'
        self.assertTrue(manifest.exists())
        data = json.loads(manifest.read_text())
        self.assertEqual(data['source_char_id'], '111')
        self.assertEqual(data['target_char_id'], '222')

    def test_restore_backup(self):
        import core.visual_clon_backup as bk_mod
        from core.visual_clon_backup import create_backup, restore_backup

        src_file = self.tmp / 'core_char_222.dat'
        src_file.write_bytes(b'\xAB' * 100)

        with patch.object(bk_mod, 'get_backup_root', return_value=self.backup_root):
            record = create_backup('111', '222', [src_file])

        src_file.write_bytes(b'\xFF' * 100)
        errors = restore_backup(record)
        self.assertEqual(errors, [])
        self.assertEqual(src_file.read_bytes(), b'\xAB' * 100)

    def test_list_backups_finds_records(self):
        import core.visual_clon_backup as bk_mod
        from core.visual_clon_backup import create_backup, list_backups

        src_file = self.tmp / 'core_char_222.dat'
        src_file.write_bytes(b'\x00' * 10)

        with patch.object(bk_mod, 'get_backup_root', return_value=self.backup_root):
            create_backup('111', '222', [src_file])
            records = list_backups()

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].source_char_id, '111')


if __name__ == '__main__':
    unittest.main()
