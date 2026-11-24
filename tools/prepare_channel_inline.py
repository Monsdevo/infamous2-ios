"""Keep atomic/fence/tag/event semantics; specialize lifted constant channels."""
HELPERS='''
void bces_channel_mfc_cmd(spu_context*ctx,uint32_t cmd){
    if(spu_mfc_atomic(ctx,cmd))return;
    mfc_submit(mfc_for(ctx),ctx,cmd);
}
void bces_channel_tag_update(spu_context*ctx,uint32_t v){
    mfc_channel_write(mfc_for(ctx),ctx,MFC_WrTagUpdate,v);
    if(v!=0 && (ctx->event_mask&1u)){spu_ev_raise(ctx,1u);spu_ch_wake(ctx);}
}
'''
def patch(source):
    assert 'void bces_channel_mfc_cmd(' not in source
    assert 'if (channel == MFC_Cmd && spu_mfc_atomic(ctx, v))' in source
    assert 'mfc_channel_write(mfc_for(ctx), ctx, channel, v);' in source
    return source+'\n'+HELPERS
