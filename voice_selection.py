def resolve_source(reference, voice_id, mode=None):
    mode = mode or ('声线库' if voice_id else '参考音频')
    if mode == '声线库':
        if not voice_id:
            raise ValueError('请先选择翻唱声线')
        return voice_id.startswith('rvc:'), None, voice_id
    if mode == '参考音频':
        if not reference:
            raise ValueError('请上传参考音频，或切换到声线库选择已训练声线')
        return False, reference, None
    raise ValueError('声线来源无效，请重新选择')
