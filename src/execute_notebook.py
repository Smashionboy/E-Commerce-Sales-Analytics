"""Execute notebook with the current interpreter, then replace only on success."""

import argparse
import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import nbformat
from jupyter_client.kernelspec import KernelSpecManager
from nbclient import NotebookClient

from .config import ROOT


class PortableNotebookClient(NotebookClient):
    """Manage the kernel without POSIX signal-handler calls on Windows.

    A finally block also cleans up kernels when startup or a cell fails.
    nbclient's default context can fail on Windows event loops that do not
    implement add_signal_handler; this notebook needs no signal hooks.
    """

    @asynccontextmanager
    async def async_setup_kernel(self, **kwargs):
        kwargs.pop("cleanup_kc", None)
        if self.km is None:
            self.create_kernel_manager()
        try:
            if not self.km.has_kernel:
                await self.async_start_new_kernel(**kwargs)
            if self.kc is None:
                await self.async_start_new_kernel_client()
            yield
        finally:
            if self.km is not None:
                await self._async_cleanup_kernel()


def save_notebook(nb, notebook: Path) -> None:
    """Validate first; replace the previous executed result only after success."""
    nbformat.validate(nb)
    temp = notebook.with_suffix(".tmp.ipynb")
    try:
        nbformat.write(nb, temp)
        os.replace(temp, notebook)
    finally:
        temp.unlink(missing_ok=True)


def execute(use_ipc: bool = False, in_process: bool = False) -> None:
    """Use current Python, a private kernelspec, and a stable working directory."""
    notebook = ROOT / "notebooks/ecommerce_analysis.ipynb"
    if in_process:
        execute_in_process(notebook)
        return
    if use_ipc and os.name == "nt":
        raise ValueError(
            "IPC transport is only supported on POSIX; omit --ipc on Windows"
        )
    with tempfile.TemporaryDirectory() as tmp:
        kernel_dir = Path(tmp) / "kernel"
        kernel_dir.mkdir()
        (kernel_dir / "kernel.json").write_text(
            json.dumps(
                {
                    "argv": [
                        sys.executable,
                        "-m",
                        "ipykernel_launcher",
                        "-f",
                        "{connection_file}",
                    ],
                    "display_name": "Olist project Python",
                    "language": "python",
                }
            ),
            encoding="utf-8",
        )
        manager = KernelSpecManager(kernel_dirs=[tmp])
        nb = nbformat.read(notebook, as_version=4)
        client = PortableNotebookClient(
            nb,
            timeout=300,
            kernel_name="kernel",
            resources={"metadata": {"path": str(ROOT)}},
        )
        client.create_kernel_manager()
        client.km.kernel_spec_manager = manager
        if use_ipc:
            client.km.transport = "ipc"
            client.km.ip = str(Path(tmp) / "connection")
        client.execute()
        nb.metadata["execution_method"] = (
            "Jupyter kernel using current Python interpreter"
        )
        save_notebook(nb, notebook)
    print("Notebook executed successfully:", notebook.name)


def execute_in_process(notebook: Path) -> None:
    """Run this pure Python notebook when kernel sockets are unavailable.

    Captures stdout and rich displays; errors abort saving. Does not validate
    the Jupyter wire protocol or support kernel-dependent widgets/magics.
    """
    from IPython.core.interactiveshell import InteractiveShell
    from IPython.utils.capture import capture_output

    shell = InteractiveShell.instance()
    nb = nbformat.read(notebook, as_version=4)
    count = 0
    for cell in nb.cells:
        if cell.cell_type != "code":
            continue
        count += 1
        with capture_output() as captured:
            result = shell.run_cell(cell.source, store_history=True)
        if result.error_before_exec or result.error_in_exec:
            raise RuntimeError(f"Notebook cell {count} failed") from (
                result.error_before_exec or result.error_in_exec
            )
        cell.execution_count = count
        cell.outputs = []
        for name, value in [("stdout", captured.stdout), ("stderr", captured.stderr)]:
            if value:
                cell.outputs.append(
                    nbformat.v4.new_output("stream", name=name, text=value)
                )
        for output in captured.outputs:
            cell.outputs.append(
                nbformat.v4.new_output(
                    "display_data", data=output.data, metadata=output.metadata
                )
            )
    nb.metadata["execution_method"] = (
        "IPython in-process; all Python cells executed; Jupyter socket transport not used"
    )
    save_notebook(nb, notebook)
    print(f"Notebook executed in-process: {count} code cells, zero errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ipc",
        action="store_true",
        help="POSIX only: use local IPC instead of TCP sockets",
    )
    parser.add_argument(
        "--in-process",
        action="store_true",
        help="Run pure Python cells with IPython without a kernel socket",
    )
    args = parser.parse_args()
    execute(args.ipc, args.in_process)
