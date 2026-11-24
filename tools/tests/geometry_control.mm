#import <Foundation/Foundation.h>
#include "GeometryControl.h"
#include <cassert>
static NSDictionary*parse(NSDictionary*d){NSData*data=[NSJSONSerialization dataWithJSONObject:d options:0 error:nil];NSString*error=nil;return bces_geometry_parse_command(data,@"current-session",&error);}
int main(){@autoreleasepool{
 NSDictionary*base=@{@"session":@"current-session",@"token":@"trial-1"};assert(parse(base));
 for(unsigned a=0;a<3;a++)for(unsigned b=0;b<3;b++){NSMutableDictionary*d=[base mutableCopy];d[@"skin"]=@(a);d[@"cull"]=@(b);d[@"validation"]=@YES;assert(parse(d));}
 for(unsigned a=0;a<3;a++)for(unsigned b=0;b<3;b++){NSMutableDictionary*d=[base mutableCopy];d[@"vertex_memo"]=@(a);d[@"texture_memo"]=@(b);assert(parse(d));}
 for(unsigned a=0;a<2;a++){NSMutableDictionary*d=[base mutableCopy];d[@"spu_dispatch"]=@(a);assert(parse(d));}
 for(id x in @[@(-1),@2,@0.5,@YES,@"1"]){NSMutableDictionary*d=[base mutableCopy];d[@"spu_dispatch"]=x;assert(!parse(d));}
 for(unsigned a=0;a<2;a++){NSMutableDictionary*d=[base mutableCopy];d[@"light_far"]=@(a);assert(parse(d));}
 for(id x in @[@(-1),@2,@0.5,@YES,@"1"]){NSMutableDictionary*d=[base mutableCopy];d[@"light_far"]=x;assert(!parse(d));}
 for(unsigned a=0;a<3;a++){NSMutableDictionary*d=[base mutableCopy];d[@"light_mask"]=@(a);assert(parse(d));}
 for(id x in @[@(-1),@3,@0.5,@YES,@"1"]){NSMutableDictionary*d=[base mutableCopy];d[@"light_mask"]=x;assert(!parse(d));}
 for(unsigned a=0;a<3;a++){NSMutableDictionary*d=[base mutableCopy];d[@"channel_inline"]=@(a);assert(parse(d));}
 for(id x in @[@(-1),@3,@0.5,@YES,@"1"]){NSMutableDictionary*d=[base mutableCopy];d[@"channel_inline"]=x;assert(!parse(d));}
 for(unsigned a=0;a<3;a++){NSMutableDictionary*d=[base mutableCopy];d[@"overlay_filter"]=@(a);assert(parse(d));}
 for(id x in @[@(-1),@3,@0.5,@YES,@"1"]){NSMutableDictionary*d=[base mutableCopy];d[@"overlay_filter"]=x;assert(!parse(d));}
 for(unsigned a=0;a<3;a++){NSMutableDictionary*d=[base mutableCopy];d[@"mfc_hint"]=@(a);assert(parse(d));}
 for(id x in @[@(-1),@3,@0.5,@YES,@"1"]){NSMutableDictionary*d=[base mutableCopy];d[@"mfc_hint"]=x;assert(!parse(d));}
 for(unsigned a=0;a<2;a++){NSMutableDictionary*d=[base mutableCopy];d[@"dma_poison_skip"]=@(a);assert(parse(d));}
 for(id x in @[@(-1),@2,@0.5,@YES,@"1"]){NSMutableDictionary*d=[base mutableCopy];d[@"dma_poison_skip"]=x;assert(!parse(d));}
 for(id badValue in @[@(-1),@3,@1.5,@YES,@"1"]){NSMutableDictionary*d=[base mutableCopy];d[@"vertex_memo"]=badValue;assert(!parse(d));d=[base mutableCopy];d[@"texture_memo"]=badValue;assert(!parse(d));}
 NSArray*bad=@[@{@"skin":@1},@{@"skin":@3,@"cull":@0,@"validation":@YES},@{@"skin":@1.5,@"cull":@0,@"validation":@YES},@{@"skin":@YES,@"cull":@0,@"validation":@YES},@{@"session":@"old-process"},@{@"token":@"../../bad"},@{@"validation":@1},@{@"frames_since":@(-1)},@{@"frames_since":@1.25},@{@"capture":@YES,@"skin":@2,@"cull":@2,@"validation":@YES},@{@"unknown":@YES}];
 for(NSDictionary*change in bad){NSMutableDictionary*d=[base mutableCopy];[d addEntriesFromDictionary:change];assert(!parse(d));}
 NSMutableDictionary*d=[base mutableCopy];d[@"frames_since"]=@1234;d[@"prepare_metal"]=@YES;assert(parse(d));
 NSString*error=nil;assert(!bces_geometry_parse_command([NSMutableData dataWithLength:4097],@"current-session",&error));puts("PASS session-bound geometry control, 9 route pairs, strict option types, unsafe/stale/partial commands rejected");return 0;
}}
