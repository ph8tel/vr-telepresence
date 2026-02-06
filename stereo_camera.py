import depthai as dai
import numpy as np
import cv2
import threading


class StereoCamera:
    def __init__(self, width=1280, height=720, fps=30):
        self.width = width
        self.height = height
        self.fps = fps

        self.pipeline = dai.Pipeline()

        # --- LEFT CAMERA ---
        self.mono_left = self.pipeline.create(dai.node.MonoCamera)
        self.mono_left.setBoardSocket(dai.CameraBoardSocket.LEFT)
        self.mono_left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_720_P)
        self.mono_left.setFps(self.fps)

        # --- RIGHT CAMERA ---
        self.mono_right = self.pipeline.create(dai.node.MonoCamera)
        self.mono_right.setBoardSocket(dai.CameraBoardSocket.RIGHT)
        self.mono_right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_720_P)
        self.mono_right.setFps(self.fps)

        # --- STEREO DEPTH (RECTIFICATION ONLY) ---
        self.stereo = self.pipeline.create(dai.node.StereoDepth)
        self.stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_ACCURACY)
        self.stereo.setRectifyEdgeFillColor(0)  # black borders
        self.stereo.setLeftRightCheck(False)
        self.stereo.setSubpixel(False)
        self.stereo.setDepthAlign(dai.CameraBoardSocket.LEFT)  # not used, but required

        # Link mono → stereo
        self.mono_left.out.link(self.stereo.left)
        self.mono_right.out.link(self.stereo.right)

        # --- OUTPUT STREAMS ---
        self.xout_left = self.pipeline.create(dai.node.XLinkOut)
        self.xout_left.setStreamName("rect_left")
        self.stereo.rectifiedLeft.link(self.xout_left.input)

        self.xout_right = self.pipeline.create(dai.node.XLinkOut)
        self.xout_right.setStreamName("rect_right")
        self.stereo.rectifiedRight.link(self.xout_right.input)

        # Runtime state
        self.device = None
        self.q_left = None
        self.q_right = None
        self.running = False
        self.frame_left = None
        self.frame_right = None

    def start(self):
        self.device = dai.Device(self.pipeline)
        self.q_left = self.device.getOutputQueue("rect_left", maxSize=4, blocking=False)
        self.q_right = self.device.getOutputQueue("rect_right", maxSize=4, blocking=False)

        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def _update(self):
        while self.running:
            inL = self.q_left.tryGet()
            inR = self.q_right.tryGet()

            if inL is not None:
                self.frame_left = inL.getCvFrame()

            if inR is not None:
                self.frame_right = inR.getCvFrame()

    def get_frames(self):
        if self.frame_left is None or self.frame_right is None:
            return None, None

        # Convert to RGB for WebRTC
        left_rgb = cv2.cvtColor(self.frame_left, cv2.COLOR_GRAY2RGB)
        right_rgb = cv2.cvtColor(self.frame_right, cv2.COLOR_GRAY2RGB)

        return left_rgb, right_rgb

    def stop(self):
        self.running = False
        if self.device:
            self.device.close()