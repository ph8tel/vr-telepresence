import depthai as dai
import numpy as np
import cv2

class StereoCamera:
    def __init__(self, size=(1280, 720)):
        self.size = size

        self.pipeline = dai.Pipeline()

        # --- Cameras (CAM_B = left, CAM_C = right) ---
        left = self.pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_B)
        right = self.pipeline.create(dai.node.Camera).build(dai.CameraBoardSocket.CAM_C)

        left_out = left.requestFullResolutionOutput(type=dai.ImgFrame.Type.NV12)
        right_out = right.requestFullResolutionOutput(type=dai.ImgFrame.Type.NV12)

        # --- StereoDepth for rectification (aligns images for VR) ---
        stereo = self.pipeline.create(dai.node.StereoDepth).build(
            left=left_out,
            right=right_out,
            presetMode=dai.node.StereoDepth.PresetMode.FAST_ACCURACY,
        )
        
        # --- Output queues for rectified images ---
        self.q_left = stereo.rectifiedLeft.createOutputQueue(blocking=False, maxSize=4)
        self.q_right = stereo.rectifiedRight.createOutputQueue(blocking=False, maxSize=4)

        # --- Start pipeline ---
        self.pipeline.start()

        print("StereoCamera initialized with OAK-Pro (rectified stereo for VR)")

    def get_frames(self):
        # Pull rectified synchronized frames
        left_msg = self.q_left.get()
        right_msg = self.q_right.get()

        frameL = left_msg.getCvFrame()
        frameR = right_msg.getCvFrame()

        # Convert grayscale → RGB to match Pi API
        frameL_rgb = cv2.cvtColor(frameL, cv2.COLOR_GRAY2RGB)
        frameR_rgb = cv2.cvtColor(frameR, cv2.COLOR_GRAY2RGB)

        # Resize to requested size if needed
        if (frameL_rgb.shape[1], frameL_rgb.shape[0]) != self.size:
            frameL_rgb = cv2.resize(frameL_rgb, self.size)
            frameR_rgb = cv2.resize(frameR_rgb, self.size)

        return frameL_rgb, frameR_rgb

    def get_stereo_frame(self):
        L, R = self.get_frames()
        return np.hstack((L, R))

    def stop(self):
        try:
            self.pipeline.stop()
        except:
            pass
    
    def get_frames_once(self):
        if not hasattr(self, "_cached"):
            self._cached = self.get_frames()
        return self._cached

    def clear_cache(self):
        if hasattr(self, "_cached"):
            del self._cached