#import <UIKit/UIKit.h>
#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#include <TargetConditionals.h>
#include "RSXMetalSurface.h"
#include "RSXSmoke.h"
#include "RuntimeProbe.h"

@interface RSXMetalView : UIView
@property(nonatomic, readonly) CAMetalLayer* metalLayer;
@end
@implementation RSXMetalView
+ (Class)layerClass { return CAMetalLayer.class; }
- (CAMetalLayer*)metalLayer { return (CAMetalLayer*)self.layer; }
@end

@interface ProbeViewController : UIViewController
- (void)drawFrame;
- (void)appendRuntime:(NSString*)line;
@end
static void runtimeLog(const char* line, void* context) {
    ProbeViewController* controller = (__bridge ProbeViewController*)context;
    NSString* message = [NSString stringWithUTF8String:line];
    // Persist each phase before the worker proceeds, so a crash in a context
    // primitive leaves its last completed phase in the app's Documents.
    dispatch_sync(dispatch_get_main_queue(), ^{ [controller appendRuntime:message]; });
}
// CADisplayLink retains its target, so keep the controller reference weak.
@interface DisplayLinkTarget : NSObject
@property(nonatomic, weak) ProbeViewController* owner;
- (void)tick:(CADisplayLink*)link;
@end
@implementation DisplayLinkTarget
- (void)tick:(CADisplayLink*)link { (void)link; [self.owner drawFrame]; }
@end

@implementation ProbeViewController {
    RSXMetalView* _metalView;
    UITextView* _status;
    NSMutableString* _report;
    NSMutableString* _runtimeReport;
    dispatch_queue_t _renderQueue;
    CADisplayLink* _displayLink;
    BOOL _started, _running, _active, _pending, _finished;
    unsigned _frame, _checks, _shaderChecks;
    BOOL _checksOK;
    BOOL _verifyResume;
    BOOL _hadPause;
    uint64_t _pausedSubmission;
}
- (void)viewDidLoad {
    [super viewDidLoad];
    _active = NO;
    _checksOK = YES;
    _report = [NSMutableString new];
    _runtimeReport = [NSMutableString new];
    _renderQueue = dispatch_queue_create("dev.infamous2.rsx-render", DISPATCH_QUEUE_SERIAL);
    self.view.backgroundColor = UIColor.blackColor;
    _metalView = [RSXMetalView new];
    _metalView.translatesAutoresizingMaskIntoConstraints = NO;
    CAMetalLayer* layer = _metalView.metalLayer;
    layer.device = MTLCreateSystemDefaultDevice();
    layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
    layer.framebufferOnly = YES;
    layer.allowsNextDrawableTimeout = YES;
    _status = [UITextView new];
    _status.translatesAutoresizingMaskIntoConstraints = NO;
    _status.editable = NO;
    _status.backgroundColor = [UIColor colorWithWhite:0.04 alpha:1];
    _status.textColor = UIColor.whiteColor;
    _status.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightRegular];
    [self.view addSubview:_metalView];
    [self.view addSubview:_status];
    UILayoutGuide* safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [_metalView.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [_metalView.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [_metalView.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor],
        [_metalView.widthAnchor constraintEqualToAnchor:safe.widthAnchor multiplier:0.45],
        [_status.leadingAnchor constraintEqualToAnchor:_metalView.trailingAnchor constant:8],
        [_status.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [_status.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [_status.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor]]];
    NSNotificationCenter* n = NSNotificationCenter.defaultCenter;
    [n addObserver:self selector:@selector(pauseRendering) name:UISceneWillDeactivateNotification object:nil];
    [n addObserver:self selector:@selector(pauseRendering) name:UISceneDidEnterBackgroundNotification object:nil];
    [n addObserver:self selector:@selector(resumeRendering) name:UISceneDidActivateNotification object:nil];
    [self append:@"RSX register-file engine -> Metal -> UIKit CAMetalLayer"];
    [self append:@"synthetic_rsx_shader=1 game_frames=0 cpu_jit=0"];
    [self append:[NSString stringWithFormat:@"shader_translation_available=%d MSL_target=iOS",
        rsx_smoke_shader_available()]];
    if (!layer.device) { [self append:@"FAIL: Metal device unavailable"]; return; }
    [self append:[NSString stringWithFormat:@"device=%@ os=%@ simulator=%d BC_support=%d",
        layer.device.name, NSProcessInfo.processInfo.operatingSystemVersionString,
        TARGET_OS_SIMULATOR, layer.device.supportsBCTextureCompression]];
}
- (void)viewDidLayoutSubviews {
    [super viewDidLayoutSubviews];
    CAMetalLayer* layer = _metalView.metalLayer;
    CGFloat scale = self.view.window.windowScene.screen.scale;
    if (scale <= 0) scale = 1;
    layer.contentsScale = scale;
    CGSize size = CGSizeMake(_metalView.bounds.size.width * scale, _metalView.bounds.size.height * scale);
    if (size.width < 1 || size.height < 1) return;
    if (!CGSizeEqualToSize(layer.drawableSize, size)) layer.drawableSize = size;
    if (_started || !layer.device) return;
    _started = YES;
    if (rsx_metal_backend_attach_ios_layer((__bridge void*)layer) != 0) {
        [self append:@"FAIL: layer attachment rejected"]; return;
    }
    dispatch_async(_renderQueue, ^{
        const int rc = rsx_smoke_init();
        dispatch_async(dispatch_get_main_queue(), ^{
            if (rc) { [self append:@"FAIL: real RSX backend initialization"]; return; }
            self->_running = YES;
            DisplayLinkTarget* target = [DisplayLinkTarget new];
            target.owner = self;
            self->_displayLink = [CADisplayLink displayLinkWithTarget:target selector:@selector(tick:)];
            self->_displayLink.preferredFrameRateRange = CAFrameRateRangeMake(30, 30, 30);
            self->_displayLink.paused = !self->_active;
            [self->_displayLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
            [self append:@"backend_initialized=1 internal_surface=640x360 UIKit_owns_drawable_size=1"];
        });
    });
}
- (void)append:(NSString*)message {
    [_report appendFormat:@"%@\n", message];
    _status.text = _report;
    [_status scrollRangeToVisible:NSMakeRange(_status.text.length, 0)];
    fprintf(stderr, "[RSX probe] %s\n", message.UTF8String);
}
- (void)saveReport {
    NSURL* documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    NSError* error = nil;
    if (![_report writeToURL:[documents URLByAppendingPathComponent:@"shader-report.txt"]
                 atomically:YES encoding:NSUTF8StringEncoding error:&error])
        [self append:[NSString stringWithFormat:@"report_write_error=%@", error.localizedDescription]];
}
- (void)appendRuntime:(NSString*)line {
    [_runtimeReport appendFormat:@"%@\n", line];
    [self append:line];
    NSURL* documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    NSError* error = nil;
    if (![_runtimeReport writeToURL:[documents URLByAppendingPathComponent:@"runtime-report.txt"]
                        atomically:YES encoding:NSUTF8StringEncoding error:&error])
        [self append:[NSString stringWithFormat:@"runtime_report_write_error=%@", error.localizedDescription]];
}
- (void)drawFrame {
    // Main owns lifecycle and queue admission; one serial queue owns all RSX
    // state. No UIKit access or per-frame GPU readback on the renderer thread.
    if (!_running || !_active || _pending) return;
    _pending = YES;
    const unsigned frame = _frame++;
    dispatch_async(_renderQueue, ^{
        @autoreleasepool {
            const uint32_t colors[] = {0xFFFF0000, 0xFF00FF00, 0xFF0000FF};
            const uint32_t swapped[] = {0xFF0000FF, 0xFF00FF00, 0xFFFF0000};
            const unsigned colorIndex = frame < 3 ? frame : frame < 6 ? frame - 3 : ((frame - 6) / 30) % 3;
            const uint32_t expected = frame < 3 ? colors[colorIndex] : swapped[colorIndex];
            uint32_t pixel = 0, translatedDraws = 0;
            if (frame < 3) pixel = rsx_smoke_present(expected, 1);
            else {
                // Hold each later colour for a second; only the first three
                // shader frames force a diagnostic GPU readback.
                RSXShaderSample sample = rsx_smoke_present_shader(colors[colorIndex], frame < 6);
                pixel = sample.pixel;
                translatedDraws = sample.translated_draws;
            }
            RSXSurfaceStats stats = rsx_metal_backend_ios_stats();
            dispatch_async(dispatch_get_main_queue(), ^{
                self->_pending = NO;
                if (frame < 6) {
                    self->_checks++;
                    BOOL passed = pixel == expected && (frame < 3 || translatedDraws == 1);
                    self->_checksOK &= passed;
                    if (frame >= 3 && passed) self->_shaderChecks++;
                    [self append:[NSString stringWithFormat:@"GPU %@ %u expected=%08X actual=%08X translated_draws=%u %@",
                        frame < 3 ? @"clear" : @"shader", frame, expected, pixel, translatedDraws,
                        passed ? @"PASS" : @"FAIL"]];
                }
                if (frame >= 30 && !self->_finished) {
                    self->_finished = YES;
                    BOOL passed = self->_checks == 6 && self->_shaderChecks == 3 && self->_checksOK &&
                        rsx_smoke_shader_available() && stats.completed >= 6 && stats.errors == 0;
#if !TARGET_OS_SIMULATOR
                    passed &= stats.presented >= 1;
#endif
                    [self append:[NSString stringWithFormat:@"surface submitted=%llu completed=%llu presented=%llu errors=%llu",
                        (unsigned long long)stats.submitted, (unsigned long long)stats.completed,
                        (unsigned long long)stats.presented, (unsigned long long)stats.errors]];
                    [self append:[NSString stringWithFormat:@"shader_result=%@ synthetic_shader_checks=%u game_frames=0",
                        passed ? @"PASS" : @"FAIL", self->_shaderChecks]];
                    [self saveReport];
                    [self appendRuntime:[NSString stringWithFormat:@"runtime_session=%@ simulator=%d", NSDate.date, TARGET_OS_SIMULATOR]];
                    dispatch_async(self->_renderQueue, ^{
                        @autoreleasepool { runtime_probe_run(runtimeLog, (__bridge void*)self); }
                    });
                }
                if (self->_verifyResume && stats.completed > self->_pausedSubmission) {
                    self->_verifyResume = NO;
                    [self append:[NSString stringWithFormat:@"lifecycle=resume_verified completed=%llu errors=%llu",
                        (unsigned long long)stats.completed, (unsigned long long)stats.errors]];
                    [self saveReport];
                }
            });
        }
    });
}
- (void)pauseRendering {
    if (!_active) return;
    _active = NO;
    _displayLink.paused = YES;
    if (_running) {
        _hadPause = YES;
        _pausedSubmission = rsx_metal_backend_ios_stats().submitted;
        [self append:@"lifecycle=paused"];
        [self saveReport];
    }
}
- (void)resumeRendering {
    if (_active) return;
    _active = YES;
    if (_running) {
        _verifyResume = _hadPause;
        _displayLink.paused = NO;
        [self append:_hadPause ? @"lifecycle=resumed" : @"lifecycle=active"];
        _hadPause = NO;
    }
}
- (void)dealloc {
    [_displayLink invalidate];
    [NSNotificationCenter.defaultCenter removeObserver:self];
    if (_started) dispatch_async(_renderQueue, ^{ rsx_smoke_shutdown(); });
}
@end

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation AppDelegate
- (BOOL)application:(UIApplication*)application didFinishLaunchingWithOptions:(NSDictionary*)options {
    (void)application; (void)options;
    fprintf(stderr, "[RSX probe] application_started simulator=%d\n", TARGET_OS_SIMULATOR);
    return YES;
}
@end
@interface ProbeSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation ProbeSceneDelegate
- (void)scene:(UIScene*)scene willConnectToSession:(UISceneSession*)session options:(UISceneConnectionOptions*)options {
    (void)session; (void)options;
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene*)scene];
    self.window.rootViewController = [ProbeViewController new];
    [self.window makeKeyAndVisible];
}
@end
int main(int argc, char** argv) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(AppDelegate.class)); }
}
