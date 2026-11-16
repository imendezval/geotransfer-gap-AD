"""Independent subprocess recorder for old/new model tensors and evaluator states."""

import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--implementation", choices=["old", "new"], required=True)
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    from geotransfer_gap.config import settings, ensure_bench, tool_path

    ensure_bench()
    if args.implementation == "old":
        from geotransfer_gap.migration import legacy_checkout

        legacy = legacy_checkout()
        sys.path.insert(0, str(legacy))
        import late_spawn_runtime as runtime

        entry = legacy / "probe_faithful_smart_closed_loop.py"
    else:
        from geotransfer_gap.runtime import late_spawn_runtime as runtime

        entry = tool_path("probe_faithful_smart_closed_loop.py")
    runtime.load()
    from pufferlib.ocean.drive.drive import Drive
    from pufferlib.prediction.binary_reader import read_binary_scenario
    from pufferlib.prediction.smart.prediction_model import PredictionModel
    from geotransfer_gap.runtime.session import frame
    import torch

    binary = read_binary_scenario(str(args.root / "testing/map_000000.bin"))
    frames = []
    inputs = []
    original_step = Drive.step
    original_close = Drive.close
    original_inference = PredictionModel.inference

    def tensor_hash(data):
        h = hashlib.sha256()

        def visit(x):
            if isinstance(x, torch.Tensor):
                a = x.detach().cpu().contiguous()
                h.update(str(a.dtype).encode())
                h.update(str(tuple(a.shape)).encode())
                h.update(a.numpy().tobytes())
            elif isinstance(x, dict):
                for k in sorted(x, key=str):
                    h.update(str(k).encode())
                    visit(x[k])
            elif isinstance(x, (list, tuple)):
                for v in x:
                    visit(v)
            else:
                h.update(repr(x).encode())

        visit(data.to_dict())
        return h.hexdigest()

    def inference(self, data, *a, **kw):
        inputs.append(tensor_hash(data))
        return original_inference(self, data, *a, **kw)

    def step(self, *a, **kw):
        frames.append(frame(self.get_state()[0], binary, len(frames)))
        return original_step(self, *a, **kw)

    def close(self, *a, **kw):
        if len(frames) < 91:
            frames.append(frame(self.get_state()[0], binary, len(frames)))
        return original_close(self, *a, **kw)

    Drive.step = step
    Drive.close = close
    PredictionModel.inference = inference
    sys.argv = [str(entry), "--root", str(args.root)]
    runpy.run_path(str(entry), run_name="__main__")
    diagnostic = json.loads(
        (
            args.root / "testing/smart_all_actors_closed_loop_hybrid_startup.json"
        ).read_text()
    )
    args.output.write_text(
        json.dumps(
            {
                "model_input_sha256": inputs,
                "frames": frames,
                "timeline": diagnostic["timeline"],
            },
            allow_nan=False,
        )
    )


if __name__ == "__main__":
    main()
