import os

import pytest
from funcy import raiser

from dvc.repo import locked


def test_is_dvc_internal(dvc):
    assert dvc.is_dvc_internal(os.path.join("path", "to", ".dvc", "file"))
    assert not dvc.is_dvc_internal(os.path.join("path", "to-non-.dvc", "file"))


@pytest.mark.parametrize(
    "path",
    [
        os.path.join("dir", "subdir", "file"),
        os.path.join("dir", "subdir"),
        "dir",
    ],
)
def test_find_outs_by_path(tmp_dir, dvc, path):
    (stage,) = tmp_dir.dvc_gen(
        {"dir": {"subdir": {"file": "file"}, "other": "other"}}
    )

    outs = dvc.find_outs_by_path(path, strict=False)
    assert len(outs) == 1
    assert outs[0].path_info == stage.outs[0].path_info


@pytest.mark.parametrize(
    "path",
    [os.path.join("dir", "subdir", "file"), os.path.join("dir", "subdir")],
)
def test_used_cache(tmp_dir, dvc, path):
    from dvc.cache import NamedCache

    tmp_dir.dvc_gen({"dir": {"subdir": {"file": "file"}, "other": "other"}})
    expected = NamedCache.make(
        "local", "70922d6bf66eb073053a82f77d58c536.dir", "dir"
    )
    expected.add_child_cache(
        "70922d6bf66eb073053a82f77d58c536.dir",
        NamedCache.make(
            "local",
            "8c7dd922ad47494fc02c388e12c00eac",
            os.path.join("dir", "subdir", "file"),
        ),
    )

    with dvc.state:
        used_cache = dvc.used_cache([path])
        assert (
            used_cache._items == expected._items
            and used_cache.external == expected.external
        )


def test_locked(mocker):
    repo = mocker.MagicMock()
    repo.method = locked(repo.method)

    args = {}
    kwargs = {}
    repo.method(repo, args, kwargs)

    assert repo.method_calls == [
        mocker.call._reset(),
        mocker.call.method(repo, args, kwargs),
        mocker.call._reset(),
    ]


def test_collect_optimization(tmp_dir, dvc, mocker):
    (stage,) = tmp_dir.dvc_gen("foo", "foo text")

    # Forget cached stages and graph and error out on collection
    dvc._reset()
    mocker.patch(
        "dvc.repo.Repo.stages",
        property(raiser(Exception("Should not collect"))),
    )

    # Should read stage directly instead of collecting the whole graph
    dvc.collect(stage.path)
    dvc.collect_granular(stage.path)


def test_collect_optimization_on_stage_name(tmp_dir, dvc, mocker, run_copy):
    tmp_dir.dvc_gen("foo", "foo")
    stage = run_copy("foo", "bar", name="copy-foo-bar")
    # Forget cached stages and graph and error out on collection
    dvc._reset()
    mocker.patch(
        "dvc.repo.Repo.stages",
        property(raiser(Exception("Should not collect"))),
    )

    # Should read stage directly instead of collecting the whole graph
    assert dvc.collect("copy-foo-bar") == [stage]
    assert dvc.collect_granular("copy-foo-bar") == [(stage, None)]


def test_skip_graph_checks(tmp_dir, dvc, mocker, run_copy):
    # See https://github.com/iterative/dvc/issues/2671 for more info
    mock_collect_graph = mocker.patch("dvc.repo.Repo._collect_graph")

    # sanity check
    tmp_dir.gen("foo", "foo text")
    dvc.add("foo")
    run_copy("foo", "bar", single_stage=True)
    assert mock_collect_graph.called

    # check that our hack can be enabled
    mock_collect_graph.reset_mock()
    dvc._skip_graph_checks = True
    tmp_dir.gen("baz", "baz text")
    dvc.add("baz")
    run_copy("baz", "qux", single_stage=True)
    assert not mock_collect_graph.called

    # check that our hack can be disabled
    mock_collect_graph.reset_mock()
    dvc._skip_graph_checks = False
    tmp_dir.gen("quux", "quux text")
    dvc.add("quux")
    run_copy("quux", "quuz", single_stage=True)
    assert mock_collect_graph.called
