"""Change only the diagnostic payload scan; all actual DMA bytes/fences stay.
No data repair or control-flow decision uses haspoison; only the diagnostic log.
"""
def patch(source):
 start=source.index('        /* POISON-DMA detector:')
 needle='          for (uint32_t o = 0; o + 4 <= size; o += 4) {'
 at=source.index(needle,start)
 assert source[start:].count(needle)==1
 result=source[:at]+source[at:].replace(needle,'          if(bces_dma_poison_scan(spu->spu_id,size))\n'+needle,1)
 assert result.replace('          if(bces_dma_poison_scan(spu->spu_id,size))\n','',1)==source
 return '#include "DmaPoisonControl.h"\n'+result
