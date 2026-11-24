#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include "CompactVertex.h"
#if BCES_VALIDATE_TRANSLATOR
#include "rsx_shader_msl.h"
#endif

static void test_pack(void) {
    // Interleaved layout slots are packed with float attributes first.
    const uint8_t source[][6] = {{0x80,0,0x7f,0xff,0,0},{0xff,0xff,0,1,0x80,1}};
    const rsx_vertex_ref refs[] = {{4,7},{5,7}};
    rsx_vertex_fetch_plan plan = {0};
    plan.layout.count = 3;
    plan.layout.stride = 48;
    plan.layout.attrs[0] = 0;
    plan.layout.attrs[1] = 2;
    plan.layout.attrs[2] = 4;
    plan.attr[2].default_value[0] = 3.25f;
    for (unsigned attr = 0; attr <= 4; attr += 4) {
        plan.attr[attr].desc.type = RSX_VTX_TYPE_SNORM16;
        plan.attr[attr].desc.size = 3;
        plan.attr[attr].stride = 6;
        plan.attr[attr].elem_size = 6;
        plan.attr[attr].stable_base = &source[0][0];
        plan.attr[attr].stable_first = 11;
        plan.attr[attr].stable_last = 12;
    }
    uint8_t original[96], packed[64];
    const uint32_t mask = bces_compact_vertex_mask(&plan, refs, 2);
    assert(mask == 17 && bces_compact_vertex_stride(&plan.layout, mask) == 32);
    assert(rsx_vertex_fetch_all(&plan, refs, 2, original));
    assert(bces_compact_vertex_pack(&plan, refs, 2, mask, packed));
    for (unsigned i = 0; i < 2; ++i) {
        assert(!memcmp(original + i*48 + 16, packed + i*32, 16));
        for (unsigned slot = 0; slot <= 2; slot += 2) {
            int16_t words[4];
            float decoded[4];
            memcpy(words, packed + i*32 + bces_compact_vertex_offset(&plan.layout, mask, slot), 8);
            for (unsigned k = 0; k < 3; ++k) decoded[k] = (float)words[k] / 32767.0f;
            decoded[3] = 1.0f;
            assert(!memcmp(original + i*48 + slot*16, decoded, 16));
        }
    }
    plan.attr[0].desc.frequency = 2;
    assert(bces_compact_vertex_mask(&plan, refs, 2) == 16);
    const rsx_vertex_ref wrapping[] = {{0xfffff,0},{0x100000,0}};
    assert(bces_compact_vertex_mask(&plan, wrapping, 2) == 0);
    char shader[256] = "v[0]=input.a0; v[4]=input.a4;";
    assert(bces_compact_vertex_shader(shader, sizeof shader, mask));
    assert(strstr(shader, "input.a0.xyz") && strstr(shader, "input.a4.xyz"));
}

static void test_gpu(void) {
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    assert(device);
    MTLCompileOptions* options = [MTLCompileOptions new];
    options.fastMathEnabled = NO;
    NSError* error = nil;
#if BCES_VALIDATE_TRANSLATOR
    char hlsl[2048] =
        "struct VSInput { float4 a0:ATTR0; };\n"
        "RWStructuredBuffer<float4> result : register(u0);\n"
        "void main(VSInput input, uint id : SV_VertexID) {\n"
        "  float4 v[16]; v[0]=input.a0; result[id]=v[0];\n"
        "}\n";
    assert(bces_compact_vertex_shader(hlsl, sizeof hlsl, 1));
    char msl[32768], diagnostics[4096];
    if (rsx_hlsl_to_msl(hlsl, RSX_SHADER_STAGE_VERTEX, msl, sizeof msl,
                        diagnostics, sizeof diagnostics) != 0) {
        fprintf(stderr, "%s\n", diagnostics);
        abort();
    }
    assert(strstr(msl, "[[buffer(0)]]"));
    const unsigned input_slot = 4, output_slot = 0;
    NSString* entry = @"main0";
    id<MTLLibrary> library = [device newLibraryWithSource:[NSString stringWithUTF8String:msl]
                                                   options:options error:&error];
#else
    const unsigned input_slot = 0, output_slot = 1;
    NSString* entry = @"probe";
    id<MTLLibrary> library = [device newLibraryWithSource:
        @"#include <metal_stdlib>\nusing namespace metal;\n"
        "struct Input { float4 a [[attribute(0)]]; };\n"
        "vertex void probe(Input in [[stage_in]], uint i [[vertex_id]], device float4* dst [[buffer(1)]]) {"
        "  dst[i] = float4(in.a.xyz*0.000030517578125f + in.a.xyz*9.31350996324909e-10f,1.0f);"
        "}" options:options error:&error];
#endif
    if (!library) NSLog(@"%@", error);
    assert(library);
    MTLVertexDescriptor* layout = [MTLVertexDescriptor vertexDescriptor];
    layout.attributes[0].format = MTLVertexFormatShort4;
    layout.attributes[0].bufferIndex = input_slot;
    layout.layouts[input_slot].stride = 8;
    MTLRenderPipelineDescriptor* desc = [MTLRenderPipelineDescriptor new];
    desc.vertexDescriptor = layout;
    desc.vertexFunction = [library newFunctionWithName:entry];
    desc.rasterizationEnabled = NO;
    desc.colorAttachments[0].pixelFormat = MTLPixelFormatRGBA8Unorm;
    id<MTLRenderPipelineState> pipeline = [device newRenderPipelineStateWithDescriptor:desc error:&error];
    if (!pipeline) NSLog(@"%@", error);
    assert(pipeline);
    id<MTLBuffer> src = [device newBufferWithLength:65536*8 options:MTLResourceStorageModeShared];
    id<MTLBuffer> dst = [device newBufferWithLength:65536*16 options:MTLResourceStorageModeShared];
    int16_t* values = src.contents;
    for (unsigned i=0; i<65536; ++i) {
        values[i*4]=(int16_t)(i-32768u);
        values[i*4+1]=(int16_t)(32767u-i);
        values[i*4+2]=(int16_t)(((i*97u)&0xffffu)-32768u);
        values[i*4+3]=0;
    }
    MTLTextureDescriptor* texture = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:
        MTLPixelFormatRGBA8Unorm width:1 height:1 mipmapped:NO];
    texture.usage=MTLTextureUsageRenderTarget;
    MTLRenderPassDescriptor* pass = [MTLRenderPassDescriptor renderPassDescriptor];
    pass.colorAttachments[0].texture = [device newTextureWithDescriptor:texture];
    id<MTLCommandQueue> queue = [device newCommandQueue];
    id<MTLCommandBuffer> cb = [queue commandBuffer];
    id<MTLRenderCommandEncoder> enc = [cb renderCommandEncoderWithDescriptor:pass];
    [enc setRenderPipelineState:pipeline];
    [enc setVertexBuffer:src offset:0 atIndex:input_slot];
    [enc setVertexBuffer:dst offset:0 atIndex:output_slot];
    [enc drawPrimitives:MTLPrimitiveTypePoint vertexStart:0 vertexCount:65536];
    [enc endEncoding];
    [cb commit];
    [cb waitUntilCompleted];
    if (cb.error) NSLog(@"%@", cb.error);
    assert(cb.status==MTLCommandBufferStatusCompleted);
    const float* actual = dst.contents;
    for (unsigned i=0; i<65536; ++i) {
        float expected[4];
        for (unsigned k=0; k<3; ++k) expected[k]=(float)values[i*4+k]/32767.0f;
        expected[3]=1.0f;
        assert(!memcmp(expected, actual+i*4, 16));
    }
}

int main(void) {
    @autoreleasepool {
        test_pack();
        test_gpu();
        puts("PASS packed layout, eligibility, shader rewrite and exhaustive Short4 GPU normalization");
    }
}
