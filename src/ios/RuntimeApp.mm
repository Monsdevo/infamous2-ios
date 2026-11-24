#import <UIKit/UIKit.h>
#import <Metal/Metal.h>
#import <QuartzCore/CAMetalLayer.h>
#include "FullRuntimeProbe.h"
#include "RSXMetalSurface.h"
#include <pthread.h>
#include <unistd.h>
@interface RuntimeMetalView : UIView
@end
@implementation RuntimeMetalView
+ (Class)layerClass { return CAMetalLayer.class; }
@end
@interface RuntimeController : UIViewController
- (void)append:(NSString*)line;
- (void)startIfReady;
- (void)pauseRuntime;
- (void)resumeRuntime;
- (void)stopRuntime;
- (void)didBackground;
- (FullRuntimeControl*)control;
- (BOOL)serial;
- (void)observeLine:(NSString*)line;
@end
static void probeLog(const char* line, void* context) {
    @autoreleasepool {
        RuntimeController* controller = (__bridge RuntimeController*)context;
        NSString* text = [NSString stringWithUTF8String:line];
        [controller append:text];
    }
}
static int waitForForeground(void* context) {
    RuntimeController* controller = (__bridge RuntimeController*)context;
    // Deliberately slow six-frame diagnostic, not a game pacing policy.
    usleep(250000);
    for (unsigned n = 0; n < 300; ++n) {
        __block BOOL active = NO;
        dispatch_sync(dispatch_get_main_queue(), ^{
            UIWindowScene* scene = controller.view.window.windowScene;
            active = scene && scene.activationState == UISceneActivationStateForegroundActive;
        });
        if (active) return 1;
        usleep(100000);
    }
    return 0;
}
static void* runPPU(void* opaque) {
    @autoreleasepool {
        NSDictionary* job = (__bridge_transfer NSDictionary*)opaque;
        RuntimeController* controller = job[@"controller"];
        NSString* elf = job[@"elf"], *vfs = job[@"vfs"];
        pthread_setname_np("inFAMOUS synthetic PPU RSX");
        char line[160];
        snprintf(line, sizeof line, "PPU_host_stack_requested=268435456 actual=%zu",
                 pthread_get_stacksize_np(pthread_self()));
        probeLog(line, (__bridge void*)controller);
        int rc;
        if (controller.serial) rc = full_runtime_probe(elf.fileSystemRepresentation, vfs.fileSystemRepresentation,
                                                       probeLog, (__bridge void*)controller, waitForForeground);
        else rc = full_runtime_probe_threaded(elf.fileSystemRepresentation, vfs.fileSystemRepresentation,
                    probeLog, (__bridge void*)controller, controller.control,
                    [job[@"frames"] unsignedIntValue], 100);
        return (void*)(intptr_t)rc;
    }
}
@implementation RuntimeController {
    RuntimeMetalView* _metal;
    UITextView* _text;
    NSMutableString* _report;
    BOOL _started, _finished, _serial, _autoTest, _stopTest, _autoDone, _hadPause;
    BOOL _workerLaunched, _workerJoined;
    unsigned _lifecycleFailures;
    FullRuntimeControl* _control;
    FullRuntimeSnapshot _paused;
    NSLock* _reportLock;
    NSURL* _reportURL;
}
- (void)viewDidLoad {
    [super viewDidLoad];
    _report = [NSMutableString new]; _reportLock = [NSLock new];
    NSArray* args = NSProcessInfo.processInfo.arguments;
    _serial = [args containsObject:@"--serial"];
    _autoTest = !_serial && [args containsObject:@"--lifecycle-test"];
    _stopTest = !_serial && [args containsObject:@"--stop-paused-test"];
    _control = _serial ? NULL : full_runtime_control_create();
    NSURL* documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    _reportURL = [documents URLByAppendingPathComponent:_serial ? @"gcm-runtime-report.txt" : @"threaded-runtime-report.txt"];
    self.view.backgroundColor = UIColor.blackColor;
    _metal = [RuntimeMetalView new]; _metal.translatesAutoresizingMaskIntoConstraints = NO;
    CAMetalLayer* layer = (CAMetalLayer*)_metal.layer;
    layer.device = MTLCreateSystemDefaultDevice();
    layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
    layer.framebufferOnly = YES; layer.allowsNextDrawableTimeout = YES;
    _text = [UITextView new]; _text.translatesAutoresizingMaskIntoConstraints = NO;
    _text.editable = NO; _text.backgroundColor = UIColor.blackColor; _text.textColor = UIColor.whiteColor;
    _text.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightRegular];
    [self.view addSubview:_metal]; [self.view addSubview:_text];
    UIStackView* buttons = [UIStackView new]; buttons.translatesAutoresizingMaskIntoConstraints = NO;
    buttons.axis = UILayoutConstraintAxisHorizontal; buttons.distribution = UIStackViewDistributionFillEqually;
    NSArray* labels = @[@"Duraklat", @"Sürdür", @"Durdur"];
    SEL selectors[] = {@selector(pauseRuntime), @selector(resumeRuntime), @selector(stopRuntime)};
    for (unsigned i = 0; i < 3; ++i) {
        UIButton* button = [UIButton buttonWithType:UIButtonTypeSystem];
        [button setTitle:labels[i] forState:UIControlStateNormal];
        [button addTarget:self action:selectors[i] forControlEvents:UIControlEventTouchUpInside];
        [buttons addArrangedSubview:button];
    }
    [self.view addSubview:buttons];
    UILayoutGuide* safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [_metal.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor],
        [_metal.centerYAnchor constraintEqualToAnchor:safe.centerYAnchor],
        [_metal.widthAnchor constraintEqualToAnchor:safe.widthAnchor multiplier:0.45],
        [_metal.heightAnchor constraintEqualToAnchor:_metal.widthAnchor multiplier:9.0/16.0],
        [_text.leadingAnchor constraintEqualToAnchor:_metal.trailingAnchor constant:8],
        [_text.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [buttons.leadingAnchor constraintEqualToAnchor:_text.leadingAnchor],
        [buttons.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [buttons.topAnchor constraintEqualToAnchor:safe.topAnchor],
        [buttons.heightAnchor constraintEqualToConstant:36],
        [_text.topAnchor constraintEqualToAnchor:buttons.bottomAnchor],
        [_text.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor]]];
    // UIKit owns the presentation size; guest render target is 640 x 360.
    layer.drawableSize = CGSizeMake(640, 360);
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(startIfReady)
        name:UISceneDidActivateNotification object:nil];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(pauseRuntime)
        name:UISceneWillDeactivateNotification object:nil];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(didBackground)
        name:UISceneDidEnterBackgroundNotification object:nil];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(stopRuntime)
        name:UISceneDidDisconnectNotification object:nil];
    [self append:_serial ? @"Adım 8: gerçek lifter + seri regresyon. Oyun karesi: 0." : @"Adım 8: gerçek lifter + PPU/renderer. Oyun karesi: 0."];
    [self append:[NSString stringWithFormat:@"session=%@ os=%@ Metal=%@", NSDate.date,
        NSProcessInfo.processInfo.operatingSystemVersionString, layer.device.name]];
}
- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated]; [self startIfReady];
}
- (void)startIfReady {
    UIWindowScene* scene = self.view.window.windowScene;
    if (!scene || scene.activationState != UISceneActivationStateForegroundActive) return;
    if (_started) { [self resumeRuntime]; return; }
    _started = YES;
    if (!((CAMetalLayer*)_metal.layer).device || rsx_metal_backend_attach_ios_layer((__bridge void*)_metal.layer)) {
        [self append:@"FAIL: CAMetalLayer attach"]; return;
    }
    NSURL* documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    NSURL* vfs = [documents URLByAppendingPathComponent:@"synthetic-vfs" isDirectory:YES];
    [NSFileManager.defaultManager createDirectoryAtURL:vfs withIntermediateDirectories:YES attributes:nil error:nil];
    NSString* elf = [NSBundle.mainBundle pathForResource:@"synthetic" ofType:@"elf"];
    if (!elf) { rsx_metal_backend_attach_ios_layer(NULL); [self append:@"FAIL: bundled synthetic ELF missing"]; return; }
    pthread_attr_t attr;
    int rc = pthread_attr_init(&attr);
    BOOL initialized = rc == 0;
    if (!rc) rc = pthread_attr_setstacksize(&attr, 256u * 1024 * 1024);
    pthread_t worker = {};
    if (!rc) {
        unsigned frames = [NSProcessInfo.processInfo.arguments containsObject:@"--background-test"] ? 200 : 12;
        NSDictionary* job = @{@"controller":self, @"elf":elf, @"vfs":vfs.path, @"frames":@(frames)};
        void* payload = (__bridge_retained void*)job;
        rc = pthread_create(&worker, &attr, runPPU, payload);
        if (rc) { NSDictionary* unused = (__bridge_transfer NSDictionary*)payload; (void)unused; }
    }
    if (initialized) pthread_attr_destroy(&attr);
    if (rc) {
        rsx_metal_backend_attach_ios_layer(NULL);
        [self append:[NSString stringWithFormat:@"FAIL: PPU host thread setup rc=%d", rc]]; return;
    }
    _workerLaunched = YES;
    // Detach the layer only AFTER GPU shutdown + join; keep main responsive.
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        void* status = NULL;
        int joined = pthread_join(worker, &status);
        dispatch_async(dispatch_get_main_queue(), ^{
            int detached = joined == 0 ? rsx_metal_backend_attach_ios_layer(NULL) : -1;
            self->_finished = YES; self->_workerJoined = joined == 0;
            BOOL stopped = (intptr_t)status == 2;
            BOOL clean = !joined && !detached && (!(intptr_t)status || stopped);
            if (self->_control) {
                FullRuntimeSnapshot snapshot = full_runtime_snapshot(self->_control);
                clean &= !snapshot.renderer_running && snapshot.renderer_idle && snapshot.ppu_finished;
            }
            if ((self->_autoTest || self->_stopTest) && !self->_autoDone) clean = NO;
            clean &= self->_lifecycleFailures == 0;
            [self append:[NSString stringWithFormat:@"lifecycle pthread_join=%d worker_result=%ld layer_detach=%d %@",
                joined, (long)(intptr_t)status, detached, clean ? @"PASS" : @"FAIL"]];
            [self append:[NSString stringWithFormat:@"lifecycle_result=%@ cancelled=%d game_frames=0",
                clean ? @"PASS" : @"FAIL", stopped]];
        });
    });
}
- (FullRuntimeControl*)control { return _control; }
- (BOOL)serial { return _serial; }
- (void)pauseRuntime {
    if (!_control || !_started || _finished || _hadPause) return;
    full_runtime_set_active(_control, 0);
    // Logging never synchronously calls main. The bounded wait lets an already
    // admitted GPU batch finish and acknowledges BOTH PPU park and GPU idle.
    BOOL idle = full_runtime_wait_quiescent(_control, 1000);
    _paused = full_runtime_snapshot(_control); _hadPause = YES;
    if (!idle) _lifecycleFailures++;
    [self append:[NSString stringWithFormat:@"lifecycle=pause acknowledged=%d jobs=%llu PPU_parked=%d GPU_idle=%d",
        idle, _paused.completed_jobs, _paused.ppu_parked, _paused.renderer_idle]];
}
- (void)resumeRuntime {
    if (!_control || _finished) return;
    UIWindowScene* scene = self.view.window.windowScene;
    if (!scene || scene.activationState != UISceneActivationStateForegroundActive) return;
    if (_hadPause) {
        FullRuntimeSnapshot now = full_runtime_snapshot(_control);
        BOOL stable = now.completed_jobs == _paused.completed_jobs && !now.renderer_busy && now.renderer_idle;
        if (!stable) _lifecycleFailures++;
        [self append:[NSString stringWithFormat:@"lifecycle=resume paused_jobs_stable=%d jobs=%llu",
            stable, now.completed_jobs]];
        _hadPause = NO;
    }
    full_runtime_set_active(_control, 1);
}
- (void)didBackground {
    if (!_control || !_started || _finished) return;
    [self pauseRuntime];
    FullRuntimeSnapshot s = full_runtime_snapshot(_control);
    BOOL idle = !s.renderer_busy && s.renderer_idle && (!s.ppu_registered || s.ppu_parked || s.ppu_finished);
    if (!idle) _lifecycleFailures++;
    [self append:[NSString stringWithFormat:@"lifecycle=background quiescent=%d jobs=%llu", idle, s.completed_jobs]];
}
- (void)stopRuntime {
    if (!_control || _finished) return;
    full_runtime_request_stop(_control);
    [self append:@"lifecycle=stop_requested cooperative=1"];
}
- (void)observeLine:(NSString*)line {
    if ((_autoTest || _stopTest) && !_autoDone && [line hasPrefix:@"GCM_frame=1 "]) {
        _autoDone = YES; [self pauseRuntime];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 300 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
            FullRuntimeSnapshot s = full_runtime_snapshot(self->_control);
            BOOL stable = s.completed_jobs == self->_paused.completed_jobs && s.renderer_idle && s.ppu_parked;
            if (!stable) self->_lifecycleFailures++;
            [self append:[NSString stringWithFormat:@"lifecycle=selftest paused_300ms_stable=%d", stable]];
            if (self->_stopTest) [self stopRuntime]; else [self resumeRuntime];
        });
    }
}
- (void)append:(NSString*)line {
    // Durable report before returning to either worker; UIKit updates are
    // asynchronous so main can wait briefly for pause without a log deadlock.
    [_reportLock lock];
    [_report appendFormat:@"%@\n", line];
    NSString* snapshot = [_report copy];
    NSError* error = nil;
    if (![snapshot writeToURL:_reportURL atomically:YES encoding:NSUTF8StringEncoding error:&error])
        fprintf(stderr, "runtime report error: %s\n", error.localizedDescription.UTF8String);
    [_reportLock unlock];
    void (^update)(void) = ^{
        // Read the latest report, avoiding an older async snapshot replacing
        // newer main-thread lifecycle lines in the display.
        [self->_reportLock lock]; NSString* current = [self->_report copy]; [self->_reportLock unlock];
        self->_text.text = current;
        [self->_text scrollRangeToVisible:NSMakeRange(current.length, 0)];
        [self observeLine:line];
    };
    if (NSThread.isMainThread) update(); else dispatch_async(dispatch_get_main_queue(), update);
}
- (void)dealloc {
    [NSNotificationCenter.defaultCenter removeObserver:self];
    // Outer join completion retains this controller until both workers exit.
    if (_control && (!_workerLaunched || _workerJoined)) full_runtime_control_destroy(_control);
}
@end
@interface AppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation AppDelegate
@end
@interface ProbeSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation ProbeSceneDelegate
- (void)scene:(UIScene*)scene willConnectToSession:(UISceneSession*)session options:(UISceneConnectionOptions*)options {
    (void)session; (void)options;
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene*)scene];
    self.window.rootViewController = [RuntimeController new]; [self.window makeKeyAndVisible];
}
@end
int main(int argc, char** argv) { @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(AppDelegate.class)); } }
