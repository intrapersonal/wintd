HAND_JOINTS = (
    "wrist",
    "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
    "index_mcp", "index_pip", "index_dip", "index_tip",
    "middle_mcp", "middle_pip", "middle_dip", "middle_tip",
    "ring_mcp", "ring_pip", "ring_dip", "ring_tip",
    "pinky_mcp", "pinky_pip", "pinky_dip", "pinky_tip",
)

HAND_BONES = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
)

TIPS = (4, 8, 12, 16, 20)
PIPS = (3, 6, 10, 14, 18)

POSE_JOINTS = (
    "nose", "l_eye_inner", "l_eye", "l_eye_outer", "r_eye_inner", "r_eye", "r_eye_outer",
    "l_ear", "r_ear", "mouth_l", "mouth_r", "l_shoulder", "r_shoulder", "l_elbow", "r_elbow",
    "l_wrist", "r_wrist", "l_pinky", "r_pinky", "l_index", "r_index", "l_thumb", "r_thumb",
    "l_hip", "r_hip", "l_knee", "r_knee", "l_ankle", "r_ankle", "l_heel", "r_heel",
    "l_foot", "r_foot",
)

POSE_BONES = (
    (11, 12), (11, 13), (13, 15), (12, 14), (14, 16), (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (27, 29), (29, 31), (24, 26), (26, 28), (28, 30), (30, 32),
    (15, 17), (15, 19), (15, 21), (16, 18), (16, 20), (16, 22), (0, 2), (0, 5), (2, 7), (5, 8),
)

FACE_POINTS = (
    ("nose", 1), ("forehead", 10), ("chin", 152),
    ("l_eye_out", 33), ("l_eye_in", 133), ("l_eye_top", 159), ("l_eye_bot", 145),
    ("r_eye_in", 362), ("r_eye_out", 263), ("r_eye_top", 386), ("r_eye_bot", 374),
    ("l_iris", 468), ("r_iris", 473),
    ("l_brow_in", 107), ("l_brow_mid", 105), ("l_brow_out", 70),
    ("r_brow_in", 336), ("r_brow_mid", 334), ("r_brow_out", 300),
    ("mouth_l", 61), ("mouth_r", 291), ("lip_top", 13), ("lip_bot", 14),
    ("lip_top_out", 0), ("lip_bot_out", 17),
    ("cheek_l", 234), ("cheek_r", 454), ("jaw_l", 172), ("jaw_r", 397),
    ("temple_l", 54), ("temple_r", 284),
)

FACE_OVAL = (
    10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365, 379, 378, 400, 377,
    152, 148, 176, 149, 150, 136, 172, 58, 132, 93, 234, 127, 162, 21, 54, 103, 67, 109,
)

LIPS = (61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146)
EYE_L = (33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7)
EYE_R = (263, 466, 388, 387, 386, 385, 384, 398, 362, 382, 381, 380, 374, 373, 390, 249)
BROW_L = (70, 63, 105, 66, 107)
BROW_R = (300, 293, 334, 296, 336)

BLENDSHAPES = (
    "_neutral", "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight",
    "cheekPuff", "cheekSquintLeft", "cheekSquintRight", "eyeBlinkLeft", "eyeBlinkRight",
    "eyeLookDownLeft", "eyeLookDownRight", "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft",
    "eyeLookOutRight", "eyeLookUpLeft", "eyeLookUpRight", "eyeSquintLeft", "eyeSquintRight",
    "eyeWideLeft", "eyeWideRight", "jawForward", "jawLeft", "jawOpen", "jawRight", "mouthClose",
    "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft", "mouthFrownRight", "mouthFunnel",
    "mouthLeft", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthPressLeft", "mouthPressRight",
    "mouthPucker", "mouthRight", "mouthRollLower", "mouthRollUpper", "mouthShrugLower",
    "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft", "mouthStretchRight",
    "mouthUpperUpLeft", "mouthUpperUpRight", "noseSneerLeft", "noseSneerRight",
)

HAND_FLAGS = (
    "present", "left", "score", "size", "palm_x", "palm_y", "angle", "vel_x", "vel_y", "speed", "push",
    "fingers", "open", "fist", "point", "peace", "spidey", "thumbsup", "pinch", "pinch_amt",
    "pinch_x", "pinch_y", "swipe_x", "swipe_y",
)

PAIR_FLAGS = ("count", "dist", "angle", "center_x", "center_y", "clap")
