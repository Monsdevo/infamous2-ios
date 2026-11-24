#import "GeometryControl.h"
#include <cmath>
NSDictionary* bces_geometry_parse_command(NSData*data,NSString*session,NSString**error){
 *error=nil;if(!data||data.length>4096){*error=@"Command missing or exceeds 4096 bytes";return nil;}
 id value=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];if(![value isKindOfClass:NSDictionary.class]){*error=@"Command must be a JSON object";return nil;}
 NSDictionary*d=value;NSSet*allowed=[NSSet setWithArray:@[@"session",@"token",@"skin",@"cull",@"validation",@"capture",@"prepare_metal",@"frames_since",@"vertex_memo",@"texture_memo",@"spu_dispatch",@"light_far",@"light_mask",@"dma_poison_skip",@"mfc_hint",@"overlay_filter",@"channel_inline",@"compact_vertex",@"gbuffer_fence"]];
 for(id key in d)if(![allowed containsObject:key]){*error=@"Unknown command field";return nil;}
 if(![d[@"session"] isKindOfClass:NSString.class]||![d[@"session"] isEqualToString:session]){*error=@"Session does not match this process";return nil;}
 NSString*token=d[@"token"];if(![token isKindOfClass:NSString.class]||token.length<1||token.length>64){*error=@"Invalid command token";return nil;}
 NSCharacterSet*bad=[[NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"] invertedSet];if([token rangeOfCharacterFromSet:bad].location!=NSNotFound){*error=@"Unsafe command token";return nil;}
 BOOL pair=d[@"skin"]||d[@"cull"]||d[@"validation"];
 if(pair&&!(d[@"skin"]&&d[@"cull"]&&d[@"validation"])){*error=@"Skin/cull/validation must be supplied together";return nil;}
 for(NSString*key in @[@"skin",@"cull",@"vertex_memo",@"texture_memo",@"mfc_hint",@"overlay_filter",@"channel_inline"])if(d[key]){
  id x=d[key];if(![x isKindOfClass:NSNumber.class]||CFGetTypeID((__bridge CFTypeRef)x)==CFBooleanGetTypeID()||[x doubleValue]<0||[x doubleValue]>2||std::floor([x doubleValue])!=[x doubleValue]){*error=@"Route must be integer 0, 1 or 2";return nil;}
 }
 for(NSString*key in @[@"validation",@"capture",@"prepare_metal"])if(d[key]&&CFGetTypeID((__bridge CFTypeRef)d[key])!=CFBooleanGetTypeID()){*error=@"Boolean option must be true/false";return nil;}
 if(d[@"spu_dispatch"]){id x=d[@"spu_dispatch"];if(![x isKindOfClass:NSNumber.class]||CFGetTypeID((__bridge CFTypeRef)x)==CFBooleanGetTypeID()||[x doubleValue]<0||[x doubleValue]>1||std::floor([x doubleValue])!=[x doubleValue]){*error=@"SPU dispatch must be integer 0 or 1";return nil;}}
 if(d[@"light_mask"]){id x=d[@"light_mask"];if(![x isKindOfClass:NSNumber.class]||CFGetTypeID((__bridge CFTypeRef)x)==CFBooleanGetTypeID()||[x doubleValue]<0||[x doubleValue]>2||std::floor([x doubleValue])!=[x doubleValue]){*error=@"Light mask must be integer 0, 1 or 2";return nil;}}
 if(d[@"dma_poison_skip"]){id x=d[@"dma_poison_skip"];if(![x isKindOfClass:NSNumber.class]||CFGetTypeID((__bridge CFTypeRef)x)==CFBooleanGetTypeID()||[x doubleValue]<0||[x doubleValue]>1||std::floor([x doubleValue])!=[x doubleValue]){*error=@"DMA poison skip must be integer 0 or 1";return nil;}}
 if(d[@"light_far"]){id x=d[@"light_far"];if(![x isKindOfClass:NSNumber.class]||CFGetTypeID((__bridge CFTypeRef)x)==CFBooleanGetTypeID()||[x doubleValue]<0||[x doubleValue]>1||std::floor([x doubleValue])!=[x doubleValue]){*error=@"Light far must be integer 0 or 1";return nil;}}
 for (NSString* field in @[@"compact_vertex",@"gbuffer_fence"]) {
     id x=d[field];
     if (!x) continue;
     if (![x isKindOfClass:NSNumber.class] || CFGetTypeID((__bridge CFTypeRef)x)==CFBooleanGetTypeID() ||
         ([x doubleValue]!=0 && [x doubleValue]!=1)) {
         *error=[NSString stringWithFormat:@"%@ must be integer 0 or 1",field];
         return nil;
     }
 }
 if([d[@"capture"] boolValue]&&pair&&([d[@"skin"] unsignedIntValue]||[d[@"cull"] unsignedIntValue])){*error=@"Reference captures require SPU/SPU";return nil;}
 if(d[@"frames_since"]){id x=d[@"frames_since"];if(![x isKindOfClass:NSNumber.class]||CFGetTypeID((__bridge CFTypeRef)x)==CFBooleanGetTypeID()||[x doubleValue]<0||[x doubleValue]>9007199254740991.0||std::floor([x doubleValue])!=[x doubleValue]){*error=@"Invalid frame sequence";return nil;}}
 return d;
}
