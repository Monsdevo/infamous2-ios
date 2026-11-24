#import <UIKit/UIKit.h>
@interface GamePerformance : NSObject
- (instancetype)initWithController:(UIViewController*)controller documents:(NSURL*)documents;
- (void)sample;
- (void)openSettings;
- (NSDictionary*)report;
- (void)applyGeometrySkin:(unsigned)skin cull:(unsigned)cull validation:(BOOL)validation;
@end
