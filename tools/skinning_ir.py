"""Static, closed pure-kernel control flow. No instruction decoding or JIT."""
import re
from prepare_skinning_reference import ROOT,MODULE

def program(root):
    text=(ROOT/'build/bces01229/spu'/MODULE/'spu_recomp.c').read_text()
    bodies={}
    for m in re.finditer(r'void '+MODULE+r'_spu_func_0000([0-9A-F]{4})\(spu_context\* ctx\) \{',text):
        end=text.index('\n}\n',m.end());bodies[int(m[1],16)]=text[m.end():end]
    reached=set();todo=[root]
    while todo:
        pc=todo.pop()
        if pc in reached or pc==0xE6C0:continue
        reached.add(pc);todo += [int(x,16) for x in re.findall(MODULE+r'_spu_func_0000([0-9A-F]{4})',bodies[pc])]
    cases={};prefix=MODULE+'_spu_func_0000'
    call=re.compile(r'ctx->gpr\[0\] = spu_link\((0x[0-9A-F]+)\); \{ int32_t _si = \(int32_t\)ctx->image_id; ctx->host_depth\+\+; '+prefix+r'([0-9A-F]{4})\(ctx\); spu_drain_call\(ctx, \1\); ctx->host_depth--; spu_img_restore\(ctx, _si\); \}')
    indirect=re.compile(r'\{ uint32_t _tg = (.*?); ctx->gpr\[0\] = spu_link\((0x[0-9A-F]+)\); int32_t _si = \(int32_t\)ctx->image_id; ctx->pc = _tg; ctx->host_depth\+\+; spu_indirect_branch\(ctx\); spu_drain_call\(ctx, \2\); ctx->host_depth--; spu_img_restore\(ctx, _si\); \}')
    branch=re.compile(r'ctx->pc = (0x[0-9A-F]+); g_spu_trampoline_fn = '+prefix+r'[0-9A-F]{4}; return;')
    def add(pc,lines):
        assert pc not in cases,hex(pc)
        code='\n'.join(lines).replace('ctx->gpr','r')
        code=code.replace('spu_ls_read128(ctx,','SK_READ(').replace('spu_ls_write128(ctx,','SK_WRITE(')
        assert not any(x in code for x in ('ctx->','g_spu_','spu_drain_call','spu_img_restore','goto ','SPU_RET')),code
        cases[pc]=code
    for start in sorted(reached):
        lines=bodies[start].splitlines();pc=start;current=[];index=0
        while index<len(lines):
            line=lines[index].strip();index+=1
            if not line:continue
            label=re.fullmatch(r'loc_0000([0-9A-F]{4}):',line)
            if label:
                target=int(label[1],16)
                if target==pc and not current:continue
                current.append(f'pc=0x{target:X}; continue;');add(pc,current);pc=target;current=[];continue
            m=call.fullmatch(line);dynamic=indirect.fullmatch(line)
            if m or dynamic:
                lr=int(m[1] if m else dynamic[2],16)
                target=f'0x{int(m[2],16):X}' if m else dynamic[1].replace('ctx->gpr','r')
                current.append(f'pc={target}; r[0]=spu_link(0x{lr:X}); continue;');add(pc,current)
                if lr in reached:
                    tail=' '.join(x.strip() for x in lines[index:] if x.strip())
                    expected=f'{{ ctx->pc = 0x{lr:X}; g_spu_trampoline_fn = {prefix}{lr:04X}; return; }}'
                    assert tail==expected,(hex(start),hex(lr),tail)
                    current=[];break
                pc=lr;current=[];continue
            line=branch.sub(lambda m:f'pc={m[1]}; continue;',line)
            m=re.fullmatch(r'if \((.*)\) goto loc_0000([0-9A-F]{4});',line)
            if m:line=f'if ({m[1]}) {{ pc=0x{m[2]}; continue; }}'
            else:line=re.sub(r'goto loc_0000([0-9A-F]{4});',lambda m:f'pc=0x{m[1]}; continue;',line)
            line=line.replace('SPU_RET(ctx);','pc=r[0]._u32[0]; continue;')
            line=re.sub(r'SPU_RET_REG\(ctx, (\d+)\);',lambda m:f'pc=r[{m[1]}]._u32[0]; continue;',line)
            current.append(line)
        if current:add(pc,current)
    cases[0xE6C0]='return 0; /* Unsupported/asserting configuration; caller retains reference state. */'
    return cases

def switch(cases):
    return '\n'.join(f'case 0x{pc:X}: {{\n{code}\nreturn 0;\n}}' for pc,code in sorted(cases.items()))

if __name__=='__main__':
    for root in (0xD0A8,0xA798):
        cases=program(root);print(hex(root),len(cases))
