# Module-level store for transcript content, shared between the
# ChatLiveView (which populates it) and the /transcript route (which serves it).

transcripts: dict[str, tuple[str, str]] = {}  # debate_id -> (content, format)
