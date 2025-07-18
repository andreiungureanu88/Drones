import cv2
import numpy as np
import torch
from depth_anything_v2.dpt import DepthAnythingV2


class DepthEstimator:
    def __init__(self):
        self.input_size = 518
        self.encoder = "vitl"
        self.load_from = "./Configuration/depth_anything_v2_metric_hypersim_vitl.pth"
        self.max_depth = 20

        self.device = 'cuda' if torch.cuda.is_available() else 'mps' if torch.backends.mps.is_available() else 'cpu'
        print(f"Using device: {self.device}")

        self.model_configs = {
            'vits': {'encoder': 'vits', 'features': 64, 'out_channels': [48, 96, 192, 384]},
            'vitb': {'encoder': 'vitb', 'features': 128, 'out_channels': [96, 192, 384, 768]},
            'vitl': {'encoder': 'vitl', 'features': 256, 'out_channels': [256, 512, 1024, 1024]},
            'vitg': {'encoder': 'vitg', 'features': 384, 'out_channels': [1536, 1536, 1536, 1536]}
        }

        if self.device == 'cpu':
            self.patch_xformers_for_cpu()

        self.depth_anything = DepthAnythingV2(**{**self.model_configs[self.encoder], 'max_depth': self.max_depth})
        self.depth_anything.load_state_dict(torch.load(self.load_from, map_location='cpu'))
        self.depth_anything = self.depth_anything.to(self.device).eval()

    def patch_xformers_for_cpu(self):

        try:
            import xformers.ops.fmha
            import math

            def cpu_attention_forward(query, key, value, attn_bias=None, p=0.0):

                query = query.float()
                key = key.float()
                value = value.float()

                scores = torch.matmul(query, key.transpose(-2, -1)) / math.sqrt(query.size(-1))

                if attn_bias is not None:
                    scores = scores + attn_bias

                attn_weights = torch.softmax(scores, dim=-1)
                if p > 0.0:
                    attn_weights = torch.nn.functional.dropout(attn_weights, p=p)

                output = torch.matmul(attn_weights, value)

                return output

            xformers.ops.fmha.memory_efficient_attention = lambda q, k, v, attn_bias=None, p=0.0: cpu_attention_forward(
                q, k, v, attn_bias, p)
            xformers.ops.fmha.memory_efficient_attention_forward = cpu_attention_forward

            print("Successfully patched xformers for CPU usage")
        except ImportError:
            print("xformers not found, using standard attention")
        except Exception as e:
            print(f"Error patching xformers: {e}")

    def process_image(self, image):
        try:
            depth = self.depth_anything.infer_image(image, self.input_size)
            depth_value = depth.mean().item()
            return depth_value
        except Exception as e:
            print(f"Error processing image: {e}")
            return None

    def calculate_side_depth(self, image, angle):
        try:
            h, w, _ = image.shape
            if angle == 90:
                side_image = image[:, :w // 2]
            elif angle == 190 or angle == 180:
                side_image = image[:, w // 2:]
            else:
                raise ValueError("Angle must be 90 (left) or 180/190 (right).")

            depth = self.depth_anything.infer_image(side_image, self.input_size)
            depth_value = depth.mean().item()
            return depth_value
        except Exception as e:
            print(f"Error calculating side depth: {e}")
            return None