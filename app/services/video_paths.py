def edited_video_object_path(*, family_id: int, question_send_id: int) -> str:
    return f"answers/{family_id}/{question_send_id}/edited.mp4"


def thumbnail_object_path(*, family_id: int, question_send_id: int) -> str:
    return f"answers/{family_id}/{question_send_id}/thumbnail.jpg"
