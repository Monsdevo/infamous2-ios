// Offline OCR of our own one-shot rendered frame; no screen/UI access.
#import <Foundation/Foundation.h>
#import <Vision/Vision.h>
int main(int argc,char**argv){@autoreleasepool{
 if(argc!=2)return 2;
 VNRecognizeTextRequest* request=[VNRecognizeTextRequest new];
 request.recognitionLevel=VNRequestTextRecognitionLevelAccurate;
 request.automaticallyDetectsLanguage=YES;
 VNImageRequestHandler* handler=[[VNImageRequestHandler alloc] initWithURL:[NSURL fileURLWithPath:[NSString stringWithUTF8String:argv[1]]] options:@{}];
 NSError* error=nil;
 if(![handler performRequests:@[request] error:&error]){fprintf(stderr,"%s\n",error.description.UTF8String);return 1;}
 NSMutableArray* rows=[NSMutableArray new];
 for(VNRecognizedTextObservation* observation in request.results){
  VNRecognizedText* text=[observation topCandidates:1].firstObject;CGRect b=observation.boundingBox;
  if(text)[rows addObject:@{@"text":text.string,@"confidence":@(text.confidence),@"box":@[@(b.origin.x),@(b.origin.y),@(b.size.width),@(b.size.height)]}];
 }
 NSData* data=[NSJSONSerialization dataWithJSONObject:rows options:NSJSONWritingPrettyPrinted error:&error];
 if(!data)return 1;fwrite(data.bytes,1,data.length,stdout);puts("");return 0;
}}
