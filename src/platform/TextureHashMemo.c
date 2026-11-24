#include "TextureHashMemo.h"
#include "RendererMemo.h"
#include <string.h>
uint64_t bces_texture_hash_memo(const uint8_t*source,uint32_t bytes,
    uint64_t(*reference)(const uint8_t*,uint32_t)){
    if(!bces_renderer_memo_mode(BCES_MEMO_TEXTURE))return reference(source,bytes);
    bces_renderer_memo_note_call(BCES_MEMO_TEXTURE);
    // Source address/length are also part of the generic memo's exact key.
    struct {uint32_t version;uint64_t(*function)(const uint8_t*,uint32_t);} key={0};
    key.version=0x54455831u;key.function=reference;
    BCESMemoInput input={source,bytes};BCESMemoTicket ticket;
    if(!bces_renderer_memo_begin(BCES_MEMO_TEXTURE,&key,sizeof(key),&input,1,sizeof(uint64_t),&ticket))return reference(source,bytes);
    uint64_t hash;
    if(!ticket.hit){hash=reference(ticket.inputs[0],bytes);memcpy(ticket.output,&hash,sizeof(hash));bces_renderer_memo_commit(BCES_MEMO_TEXTURE,&ticket,1);}
    else memcpy(&hash,ticket.output,sizeof(hash));
    if(ticket.mode==2){uint64_t actual=reference(source,bytes);bces_renderer_memo_validation(BCES_MEMO_TEXTURE,&ticket,actual==hash);return actual;}
    return hash;
}
