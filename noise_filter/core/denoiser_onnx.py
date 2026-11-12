"""ONNX neural denoiser wrapper (CPU, no GPU needed at runtime).

The model is trained offline (see training/) and exported to ONNX. Expected
interface: input  "frame"     float32 [1, FRAME_SIZE]
           output "frame_out" float32 [1, FRAME_SIZE]   ("frame" is accepted for older models)
Recurrent models keep their own state via extra inputs/outputs named "state*",
paired in order (first state input <- first state output). The C++ port in
cpp/src/onnx_denoiser.cpp follows the same contract.
"""
import numpy as np
from .constants import FRAME_SIZE


class OnnxDenoiser:
    def __init__(self, model_path: str, threads: int = 1):
        import onnxruntime as ort  # optional dependency
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = threads
        opts.inter_op_num_threads = 1
        self.sess = ort.InferenceSession(model_path, opts, providers=["CPUExecutionProvider"])
        ins = {i.name: i for i in self.sess.get_inputs()}
        self.state_in = [n for n in ins if n.startswith("state")]
        self.state = {n: np.zeros([d if isinstance(d, int) else 1 for d in ins[n].shape],
                                  np.float32) for n in self.state_in}
        outs = [o.name for o in self.sess.get_outputs()]
        self.state_out = [n for n in outs if n.startswith("state")]
        self.out_name = "frame_out" if "frame_out" in outs else "frame"

    def process(self, x: np.ndarray) -> np.ndarray:
        feeds = {"frame": x.reshape(1, FRAME_SIZE).astype(np.float32), **self.state}
        outs = self.sess.run(None, feeds)
        names = [o.name for o in self.sess.get_outputs()]
        res = dict(zip(names, outs))
        for sin, sout in zip(self.state_in, self.state_out):
            self.state[sin] = res[sout]
        return res[self.out_name].reshape(FRAME_SIZE)
