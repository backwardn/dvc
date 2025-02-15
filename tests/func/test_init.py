import logging
import os

from dvc.config import Config
from dvc.exceptions import InitError
from dvc.main import main
from dvc.repo import Repo as DvcRepo
from tests.basic_env import TestDir, TestGit


class TestInit(TestGit):
    def _test_init(self):
        self.assertTrue(os.path.exists(DvcRepo.DVC_DIR))
        self.assertTrue(os.path.isdir(DvcRepo.DVC_DIR))

    def test_api(self):
        DvcRepo.init()

        self._test_init()

    def test_cli(self):
        ret = main(["init"])
        self.assertEqual(ret, 0)

        self._test_init()


class TestDoubleInit(TestInit):
    def test(self):
        ret = main(["init"])
        self.assertEqual(ret, 0)
        self._test_init()

        ret = main(["init"])
        self.assertNotEqual(ret, 0)
        self._test_init()

        ret = main(["init", "--force"])
        self.assertEqual(ret, 0)
        self._test_init()


class TestInitNoSCMFail(TestDir):
    def test_api(self):
        with self.assertRaises(InitError):
            DvcRepo.init()

    def test_cli(self):
        ret = main(["init"])
        self.assertNotEqual(ret, 0)


def test_init_no_scm_api(tmp_dir):
    repo = DvcRepo.init(no_scm=True)

    assert (tmp_dir / DvcRepo.DVC_DIR).is_dir()
    assert repo.config["core"]["no_scm"]


def test_init_no_scm_cli(tmp_dir):
    ret = main(["init", "--no-scm"])
    assert ret == 0

    dvc_path = tmp_dir / DvcRepo.DVC_DIR
    assert dvc_path.is_dir()
    assert Config(os.fspath(dvc_path))["core"]["no_scm"]


def test_init_quiet_should_not_display_welcome_screen(tmp_dir, scm, caplog):
    with caplog.at_level(logging.INFO, logger="dvc"):
        ret = main(["init", "--quiet"])

        assert 0 == ret
        assert "" == caplog.text


def test_allow_init_dvc_subdir(tmp_dir, scm, monkeypatch):
    tmp_dir.gen({"subdir": {}})

    with monkeypatch.context() as m:
        m.chdir("subdir")
        assert main(["init", "--subdir"]) == 0

    repo = DvcRepo("subdir")
    assert repo.root_dir == os.fspath(tmp_dir / "subdir")
    assert repo.scm.root_dir == os.fspath(tmp_dir)


def test_subdir_init_no_option(tmp_dir, scm, monkeypatch, caplog):
    tmp_dir.gen({"subdir": {}})

    caplog.clear()
    with monkeypatch.context() as m:
        m.chdir("subdir")
        with caplog.at_level(logging.ERROR, logger="dvc"):
            assert main(["init"]) == 1

    assert (
        "{} is not tracked by any supported SCM tool (e.g. Git). "
        "Use `--no-scm` if you don't want to use any SCM or "
        "`--subdir` if initializing inside a subdirectory of a parent SCM "
        "repository.".format(os.fspath(tmp_dir / "subdir"))
    ) in caplog.text
