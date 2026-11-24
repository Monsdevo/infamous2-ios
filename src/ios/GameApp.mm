#include "DmaPoisonControl.h"
#include "MfcHintControl.h"
#include "MfcLayout.h"
#include "OverlayFilterControl.h"
#include "SpuChannelControl.h"
#include "HostLightMask.h"
#include "MetalLighting.h"
#include "MetalSSAO.h"
#include "SSAODepthBoundary.h"
#include "EdgeGeometry.h"
#include "EdgeFlow.h"
#include "Skinning.h"
#include "LightingValidation.h"
#include "FrameTrace.h"
#include "CriticalJobTrace.h"
#include "CriticalJobFlow.h"
#if BCES_GBUFFER_FENCE
#include "GBufferFence.h"
#endif
#if BCES_HALF_DEPTH_PROBE
#include "HalfDepthProbe.h"
#endif
#include "CompactVertex.h"
#include "ProgressTrace.h"
#include "SpuDispatchControl.h"
#include "LightingFarReject.h"
#include "CPUProfile.h"
#include "HostStack.h"
#define SDL_MAIN_HANDLED
#import <UIKit/UIKit.h>
#import <Metal/Metal.h>
#import <GameController/GameController.h>
#import <QuartzCore/CAMetalLayer.h>
#import <CommonCrypto/CommonDigest.h>
#include <SDL.h>
#include "BCESIOS.h"
#include "BCESSpuCopy.h"
#include "ShaderDiagnostics.h"
#import "GamePerformance.h"
#include "RSXMetalSurface.h"
#include "GameTelemetry.h"
#include "GeometryKernels.h"
#include "GeometryMetalBatches.h"
#include "GeometryControl.h"
#include "RSXLegacyFastPath.h"
#include "RendererMemo.h"
#include <memory>
#include <mach/mach.h>
#include <pthread.h>
#include <sys/stat.h>
#include <sys/statvfs.h>
#include <errno.h>
#include <fcntl.h>
#include <unistd.h>
#ifndef BCES_SUPPORT_VARIANT
#define BCES_SUPPORT_VARIANT "unknown"
#endif

static NSString* Digest(NSURL* url) {
    if (!url) return nil;
    NSInputStream* input = [NSInputStream inputStreamWithURL:url];
    [input open]; CC_SHA256_CTX state; CC_SHA256_Init(&state);
    uint8_t bytes[64 * 1024]; NSInteger n;
    while ((n = [input read:bytes maxLength:sizeof bytes]) > 0) CC_SHA256_Update(&state, bytes, (CC_LONG)n);
    [input close]; if (n < 0) return nil;
    uint8_t hash[CC_SHA256_DIGEST_LENGTH]; CC_SHA256_Final(hash, &state);
    NSMutableString* value = [NSMutableString string];
    for (unsigned i = 0; i < sizeof hash; ++i) [value appendFormat:@"%02x", hash[i]];
    return value;
}
static NSDictionary* RendererMemoReport(unsigned kind) {
    BCESMemoStats s=bces_renderer_memo_stats(kind);
    return @{@"mode":@(s.mode),@"calls":@(s.calls),@"lookups":@(s.lookups),@"hits":@(s.hits),
             @"misses":@(s.misses),@"bypasses":@(s.bypasses),@"evictions":@(s.evictions),
             @"validations":@(s.validations),@"mismatches":@(s.mismatches),
             @"compared_bytes":@(s.compared_bytes),@"snapshot_bytes":@(s.snapshot_bytes),
             @"output_bytes":@(s.output_bytes),@"resident_bytes":@(s.resident_bytes)};
}
@interface GameMetalView : UIView
@end
@implementation GameMetalView
+ (Class)layerClass { return CAMetalLayer.class; }
@end

@interface GameController : UIViewController
- (void)writeReport;
- (void)geometryControl;
- (void)gameDidReturn:(int)rc;
@end
@implementation GameController {
    GameMetalView* _metal;
    UIView* _setup;
    UILabel* _status;
    UILabel* _hud;
    GamePerformance* _performance;
    UIButton* _start;
    UIButton* _refresh;
    NSURL* _documents;
    NSURL* _vfs;
    NSURL* _reportURL;
    NSMutableDictionary* _report;
    BOOL _checking, _ready, _booted, _linkChecked, _showedSettings;
    int _linkResult;
    NSTimer* _timer;
    NSUInteger _ticks, _duration;
    BOOL _geometryControlEnabled;
    NSString* _geometryControlSession;
    NSString* _geometryControlToken;
}
- (void)viewDidLoad {
    [super viewDidLoad]; self.view.backgroundColor = UIColor.blackColor;
    _documents = [NSFileManager.defaultManager URLsForDirectory:NSDocumentDirectory inDomains:NSUserDomainMask].firstObject;
    _vfs = [_documents URLByAppendingPathComponent:@"BCES01229" isDirectory:YES];
    _reportURL = [_documents URLByAppendingPathComponent:@"bces-device-report.json"];
    [NSFileManager.defaultManager createDirectoryAtURL:_vfs withIntermediateDirectories:YES attributes:nil error:nil];
    _report = [@{@"profile":@"BCES01229-01.00", @"game_booted":@NO, @"device_game_image_verified":@NO,
                  @"pid":@(getpid()), @"CPU_JIT":@NO, @"session":NSDate.date.description,
                  @"support_build_variant":@BCES_SUPPORT_VARIANT} mutableCopy];
    NSString* log = [_documents URLByAppendingPathComponent:@"bces-runtime.log"].path;
    if ([NSFileManager.defaultManager fileExistsAtPath:log]) {
        NSString* old = [_documents URLByAppendingPathComponent:@"bces-runtime-previous.log"].path;
        [NSFileManager.defaultManager removeItemAtPath:old error:nil];
        [NSFileManager.defaultManager moveItemAtPath:log toPath:old error:nil];
    }
    freopen(log.fileSystemRepresentation, "w", stdout);
    dup2(fileno(stdout), STDERR_FILENO); setvbuf(stdout, NULL, _IONBF, 0);
    _metal = [GameMetalView new]; _metal.translatesAutoresizingMaskIntoConstraints = NO;
    CAMetalLayer* layer = (CAMetalLayer*)_metal.layer;
    layer.device = MTLCreateSystemDefaultDevice(); layer.pixelFormat = MTLPixelFormatBGRA8Unorm;
    layer.framebufferOnly = YES; layer.allowsNextDrawableTimeout = YES;
    layer.drawableSize = CGSizeMake(1280, 720); // Same guest/render baseline as Mac, no 3x retina target.
    _report[@"Metal_device"] = layer.device.name ?: @"unavailable";
    [self.view addSubview:_metal];
    _setup = [UIView new]; _setup.translatesAutoresizingMaskIntoConstraints = NO;
    _setup.backgroundColor = UIColor.blackColor;
    _status = [UILabel new]; _status.numberOfLines = 0; _status.textColor = UIColor.whiteColor;
    _status.font = [UIFont monospacedSystemFontOfSize:13 weight:UIFontWeightRegular];
    _status.text = @"inFAMOUS 2 — oyun girdileri denetleniyor…";
    _start = [UIButton buttonWithType:UIButtonTypeSystem]; [_start setTitle:@"Oyunu başlat" forState:UIControlStateNormal];
    [_start addTarget:self action:@selector(startGame) forControlEvents:UIControlEventTouchUpInside]; _start.enabled = NO;
    _refresh = [UIButton buttonWithType:UIButtonTypeSystem]; [_refresh setTitle:@"Dosyaları denetle" forState:UIControlStateNormal];
    [_refresh addTarget:self action:@selector(checkInputs) forControlEvents:UIControlEventTouchUpInside];
    UIStackView* stack = [[UIStackView alloc] initWithArrangedSubviews:@[_status, _start, _refresh]];
    stack.axis = UILayoutConstraintAxisVertical; stack.spacing = 12; stack.translatesAutoresizingMaskIntoConstraints = NO;
    [_setup addSubview:stack]; [self.view addSubview:_setup];
    _hud = [UILabel new]; _hud.translatesAutoresizingMaskIntoConstraints = NO; _hud.numberOfLines = 2;
    _hud.textColor = UIColor.whiteColor; _hud.backgroundColor = [UIColor colorWithWhite:0 alpha:0.65];
    _hud.font = [UIFont monospacedSystemFontOfSize:10 weight:UIFontWeightRegular]; _hud.hidden = YES;
    [self.view addSubview:_hud]; UILayoutGuide* safe = self.view.safeAreaLayoutGuide;
    [NSLayoutConstraint activateConstraints:@[
        [_metal.centerXAnchor constraintEqualToAnchor:self.view.centerXAnchor],
        [_metal.centerYAnchor constraintEqualToAnchor:self.view.centerYAnchor],
        [_metal.widthAnchor constraintLessThanOrEqualToAnchor:safe.widthAnchor],
        [_metal.heightAnchor constraintLessThanOrEqualToAnchor:safe.heightAnchor],
        [_metal.heightAnchor constraintEqualToAnchor:_metal.widthAnchor multiplier:9.0/16.0],
        [_setup.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor], [_setup.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor],
        [_setup.topAnchor constraintEqualToAnchor:safe.topAnchor], [_setup.bottomAnchor constraintEqualToAnchor:safe.bottomAnchor],
        [stack.leadingAnchor constraintEqualToAnchor:_setup.leadingAnchor constant:20],
        [stack.trailingAnchor constraintEqualToAnchor:_setup.trailingAnchor constant:-20], [stack.centerYAnchor constraintEqualToAnchor:_setup.centerYAnchor],
        [_hud.topAnchor constraintEqualToAnchor:safe.topAnchor], [_hud.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor]]];
    NSLayoutConstraint* width = [_metal.widthAnchor constraintEqualToAnchor:safe.widthAnchor]; width.priority = 750; width.active = YES;
    if([NSProcessInfo.processInfo.arguments containsObject:@"--geometry-control"]){
        // A test process always boots the reference configuration. Old files
        // cannot apply because every launch has a new control nonce.
        NSUserDefaults*d=NSUserDefaults.standardUserDefaults;for(NSString*name in @[@"skin-arm64",@"skin-metal",@"cull-arm64",@"cull-metal"])[d setBool:NO forKey:[@"performance." stringByAppendingString:name]];
        _geometryControlEnabled=YES;_geometryControlSession=NSUUID.UUID.UUIDString;
        _report[@"geometry_control_enabled"]=@YES;_report[@"geometry_control_session"]=_geometryControlSession;
    }
    _performance=[[GamePerformance alloc] initWithController:self documents:_documents];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(deactivate) name:UISceneWillDeactivateNotification object:nil];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(activate) name:UISceneDidActivateNotification object:nil];
    NSArray* args = NSProcessInfo.processInfo.arguments;
    if ([args containsObject:@"--diagnose-frame"]) bces_frame_trace_configure(_documents.path.fileSystemRepresentation);
#if BCES_HALF_DEPTH_PROBE
    if ([args containsObject:@"--diagnose-frame"]) bces_half_depth_configure(_documents.path.fileSystemRepresentation);
#endif
    BOOL jobPhases=BCES_JOB_FLOW && BCES_JOB_PHASES && [args containsObject:@"--diagnose-job-phases"];
    BOOL jobFlow=jobPhases || (BCES_JOB_FLOW && [args containsObject:@"--diagnose-job-flow"]);
    BOOL criticalJob=jobFlow || [args containsObject:@"--diagnose-critical-job"];
    bces_critical_job_enable(criticalJob);
    bces_critical_flow_enable(jobFlow);
    bces_critical_phases_enable(jobPhases);
    _report[@"critical_job_phases_requested"]=@(jobPhases);
    _report[@"critical_job_flow_requested"]=@(jobFlow);
    if(criticalJob)bces_progress_trace_set_compact(2);
    _report[@"critical_job_trace_requested"]=@(criticalJob);
    _report[@"critical_job_trace_compiled"]=@(BCES_CRITICAL_JOB_TRACE);
    _report[@"critical_job_whole_jobs_compiled"]=@(BCES_CRITICAL_WHOLE_JOBS);
    _report[@"critical_job_logical_jobs_compiled"]=@(BCES_CRITICAL_LOGICAL_JOBS);
    _report[@"progress_trace_compact"]=@(bces_progress_trace_compact());
    if ([args containsObject:@"--profile-cpu"]) bces_cpu_profile_configure(_documents.path.fileSystemRepresentation);
    if ([args containsObject:@"--diagnose-ssao-depth"]) bces_ssao_depth_control_configure(_documents.path.fileSystemRepresentation);
    if ([args containsObject:@"--diagnose-edge"]) bces_edge_control_configure(_documents.path.fileSystemRepresentation);
    if ([args containsObject:@"--diagnose-shaders"])
        bces_shader_diagnostics_configure(_documents.path.fileSystemRepresentation);
    NSUInteger index = [args indexOfObject:@"--seconds"];
    if (index != NSNotFound && index + 1 < args.count) _duration = MIN(600, [args[index + 1] integerValue]);
    _timer = [NSTimer timerWithTimeInterval:1 target:self selector:@selector(tick) userInfo:nil repeats:YES];
    [NSRunLoop.mainRunLoop addTimer:_timer forMode:NSRunLoopCommonModes];
    bces_light_validation_configure(_documents.path.fileSystemRepresentation, [args containsObject:@"--validate-lit-lighting"] ? 2 : [args containsObject:@"--validate-lighting"]);
    if([args containsObject:@"--replay-lighting-fixtures"])bces_light_validation_replay(_documents.path.fileSystemRepresentation);
    [self checkInputs];
}
- (void)checkInputs {
    if (_checking || _booted) return;
    _checking = YES; _refresh.enabled = NO; _start.enabled = NO;
    _status.text = @"Oyun ve cihaz bağlantısı denetleniyor…";
    NSURL* manifestURL = [NSBundle.mainBundle URLForResource:@"bces-inputs" withExtension:@"json"];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
        @autoreleasepool {
            NSDictionary* manifest = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfURL:manifestURL] options:0 error:nil];
            int linked = self->_linkChecked ? self->_linkResult : bces_ios_validate_link();
            NSUInteger missing = 0, mismatched = 0; NSMutableArray* examples = [NSMutableArray new];
            for (NSDictionary* entry in manifest[@"entries"]) {
                NSURL* file = [self->_vfs URLByAppendingPathComponent:entry[@"path"]];
                NSDictionary* attrs = [NSFileManager.defaultManager attributesOfItemAtPath:file.path error:nil];
                BOOL ok = attrs && [attrs[NSFileSize] unsignedLongLongValue] == [entry[@"bytes"] unsignedLongLongValue];
                if (ok && entry[@"sha256"]) ok = [Digest(file) isEqualToString:entry[@"sha256"]];
                if (!ok) { if (!attrs) ++missing; else ++mismatched; if (examples.count < 6) [examples addObject:entry[@"path"]]; }
            }
            NSURL* elf = [NSBundle.mainBundle URLForResource:@"EBOOT" withExtension:@"elf"];
            BOOL elfOK = [Digest(elf) isEqualToString:manifest[@"elf_sha256"]];
            NSData* tokenData = [NSData dataWithContentsOfURL:[self->_vfs URLByAppendingPathComponent:@"transfer-complete.json"]];
            NSDictionary* token = tokenData ? [NSJSONSerialization JSONObjectWithData:tokenData options:0 error:nil] : nil;
            BOOL transferComplete = [token[@"manifest_sha256"] isEqualToString:Digest(manifestURL)];
            NSNumber* free = nil;
            [self->_documents getResourceValue:&free forKey:NSURLVolumeAvailableCapacityForImportantUsageKey error:nil];
            if (!free) free = [NSFileManager.defaultManager attributesOfFileSystemForPath:self->_documents.path error:nil][NSFileSystemFreeSize];
            BOOL ready = manifest && [manifest[@"entries"] count] >= 194 && !linked && elfOK && transferComplete && !missing && !mismatched;
            dispatch_async(dispatch_get_main_queue(), ^{
                self->_checking = NO; self->_linkChecked = YES; self->_linkResult = linked; self->_ready = ready;
                self->_report[@"link_validation_passed"] = @(!linked); self->_report[@"bundled_ELF_verified"] = @(elfOK);
                self->_report[@"missing_files"] = @(missing); self->_report[@"mismatched_files"] = @(mismatched);
                self->_report[@"missing_examples"] = examples; self->_report[@"inputs_ready"] = @(ready);
                self->_report[@"transfer_complete"] = @(transferComplete);
                self->_report[@"required_asset_bytes"] = manifest[@"total_bytes"] ?: @0;
                self->_report[@"available_capacity_bytes"] = free ?: @0;
                self->_refresh.enabled = YES; self->_start.enabled = ready;
                self->_status.text = ready ? @"inFAMOUS 2 hazır.\nFiziksel kontrolcüyle denemek için oyunu başlatabilirsin." :
                    [NSString stringWithFormat:@"inFAMOUS 2\nOyun bağlantısı: %@\nEksik dosya: %lu — uyumsuz: %lu\nAktarım tamamlanınca yeniden denetle.",
                     linked ? @"başarısız" : @"hazır", (unsigned long)missing, (unsigned long)mismatched];
                [self writeReport];
                if (ready && [NSProcessInfo.processInfo.arguments containsObject:@"--boot"]) [self startGame];
            });
        }
    });
}
- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    UIApplication.sharedApplication.idleTimerDisabled = [NSUserDefaults.standardUserDefaults boolForKey:@"performance.awake"];
    if (!_showedSettings && [NSProcessInfo.processInfo.arguments containsObject:@"--show-settings"]) {
        _showedSettings = YES;
        [_performance performSelector:@selector(openSettings) withObject:nil afterDelay:0.5];
    }
}
static void* gameWorker(void* opaque) {
    @autoreleasepool {
        GameController* controller = (__bridge_transfer GameController*)opaque;
        pthread_setname_np("inFAMOUS BCES real PPU");
        bces_host_stack_register();
        bces_frame_trace_register_ppu(1);
        fprintf(stderr, "[bces-ios] real_PPU_stack=%zu CPU_JIT=0\n", pthread_get_stacksize_np(pthread_self()));
        NSString* elf = [NSBundle.mainBundle pathForResource:@"EBOOT" ofType:@"elf"];
        char name[] = "Infamous2Game"; char* args[] = {name, const_cast<char*>(elf.fileSystemRepresentation), nullptr};
        int rc = bces_game_main(2, args);
        dispatch_async(dispatch_get_main_queue(), ^{
            [controller gameDidReturn:rc];
        });
        return nullptr;
    }
}
- (void)gameDidReturn:(int)rc {
    _report[@"guest_main_returned"] = @(rc); [self writeReport];
    _hud.text = @"Oyun süreci döndü. Yeni deneme için uygulamayı yeniden aç.";
}
- (void)startGame {
    if (!_ready || _booted || self.view.window.windowScene.activationState != UISceneActivationStateForegroundActive) return;
    if (rsx_metal_backend_attach_ios_layer((__bridge void*)_metal.layer)) {
        _status.text = @"Metal yüzeyi bağlanamadı."; return;
    }
    for (NSString* component in @[@"dev_hdd0", @"saves"]) {
        [NSFileManager.defaultManager createDirectoryAtURL:[_vfs URLByAppendingPathComponent:component] withIntermediateDirectories:YES attributes:nil error:nil];
    }
    // cellGame's guest-path-sized host buffers are only 128 bytes. The iOS
    // container prefix plus BCES01143_INSTALL already needs 129 including NUL.
    // A process-local VFS cwd keeps host paths short without changing guest ABI.
    if (chdir(_vfs.path.fileSystemRepresentation)) {
        _status.text = @"Oyun veri klasörüne erişilemedi."; return;
    }
    struct statvfs disk = {}; int diskRC = statvfs("dev_hdd0", &disk);
    fprintf(stderr, "[bces-ios] VFS cwd set; statvfs rc=%d errno=%d block=%lu bavail=%llu bfree=%llu\n",
            diskRC, diskRC ? errno : 0, disk.f_frsize, (unsigned long long)disk.f_bavail, (unsigned long long)disk.f_bfree);
    setenv("PS3_VFS_ROOT", ".", 1);
    setenv("PS3_HDD0_ROOT", "dev_hdd0", 1);
    setenv("PS3_DEV_FLASH", "dev_flash", 1);
    setenv("PS3_GAMEDATA_ROOT", "saves", 1);
    setenv("PS3_BOOT_PATH", "/dev_bdvd/PS3_GAME/USRDIR/EBOOT.BIN", 1);
    BOOL rsxLegacyFast=[NSUserDefaults.standardUserDefaults boolForKey:@"performance.rsx-legacy-fast"];
    NSArray* launchArgs=NSProcessInfo.processInfo.arguments;
    if([launchArgs containsObject:@"--rsx-legacy-off"])rsxLegacyFast=NO;
    else if([launchArgs containsObject:@"--rsx-legacy-on"])rsxLegacyFast=YES;
    bces_rsx_legacy_configure(rsxLegacyFast);
    // Exact-input caches are opt-in for this experiment. Launch overrides do
    // not change any saved user setting; live commands require a separate flag.
    bces_renderer_memo_set(BCES_MEMO_VERTEX,[launchArgs containsObject:@"--vertex-memo-on"]?1:0);
    bces_renderer_memo_set(BCES_MEMO_TEXTURE,[launchArgs containsObject:@"--texture-memo-on"]?1:0);
    _report[@"renderer_memo_control_enabled"]=@([launchArgs containsObject:@"--renderer-memo-control"]);
#if BCES_GBUFFER_FENCE
    _report[@"gbuffer_fence_control_enabled"]=@([launchArgs containsObject:@"--gbuffer-fence-control"]);
#endif
    _report[@"compact_vertex_control_enabled"]=@(BCES_COMPACT_VERTEX &&
        [launchArgs containsObject:@"--compact-vertex-control"]);
    BOOL combined=[NSUserDefaults.standardUserDefaults boolForKey:@"performance.verified-fast-paths"];
    if([launchArgs containsObject:@"--combined-off"])combined=NO;
    _report[@"combined_optimizations_requested"]=@(combined);
    if(combined){[NSUserDefaults.standardUserDefaults setBool:YES forKey:@"performance.metal-lighting"];[NSUserDefaults.standardUserDefaults setBool:YES forKey:@"performance.metal-ssao"];[_performance applyGeometrySkin:0 cull:0 validation:NO];}
    bces_mask_set([launchArgs containsObject:@"--light-mask-validate"]?2:combined?1:0);
    _report[@"light_mask_control_enabled"]=@([launchArgs containsObject:@"--light-mask-control"]);
    bces_dma_poison_configure();
    bces_mfc_hint_set([launchArgs containsObject:@"--mfc-hint-on"]?1:0);
    bces_channel_configure();bces_channel_set([launchArgs containsObject:@"--channel-inline-on"]?1:0);
    _report[@"channel_inline_control_enabled"]=@([launchArgs containsObject:@"--channel-inline-control"]);
    bces_overlay_filter_set([launchArgs containsObject:@"--overlay-filter-on"]?1:0);
    _report[@"overlay_filter_control_enabled"]=@([launchArgs containsObject:@"--overlay-filter-control"]);
    _report[@"mfc_hint_control_enabled"]=@([launchArgs containsObject:@"--mfc-hint-control"]);
    bces_dma_poison_set([launchArgs containsObject:@"--dma-poison-skip"] || [NSUserDefaults.standardUserDefaults boolForKey:@"performance.dma-poison-skip"]);
    _report[@"dma_poison_control_enabled"]=@([launchArgs containsObject:@"--dma-poison-control"]);
    BOOL dispatchControl=[launchArgs containsObject:@"--spu-dispatch-control"];
    bces_spu_dispatch_set(combined || [launchArgs containsObject:@"--spu-dispatch-on"],dispatchControl);
    _report[@"spu_dispatch_control_enabled"]=@(dispatchControl);
    bces_light_far_set(combined || [launchArgs containsObject:@"--light-far-on"]);
    _report[@"light_far_control_enabled"]=@([launchArgs containsObject:@"--light-far-control"]);
    _report[@"rsx_legacy_fast_requested"]=@(rsxLegacyFast);
    setenv("GCM_SEMA_ACQUIRE", "1", 1); setenv("GCM_SEMA_ACQUIRE_MS", "200", 1); setenv("GCM_PARK_GRACE_MS", "1000", 1);
    BOOL metalLight=[NSUserDefaults.standardUserDefaults boolForKey:@"performance.metal-lighting"] && ![NSProcessInfo.processInfo.arguments containsObject:@"--spu-lighting"];
    _report[@"metal_lighting_requested"]=@(metalLight);
    setenv("PS3RECOMP_ENG_GPU_LIGHT", metalLight ? "06FF3B80:07377B80" : "", 1);
    BOOL metalSSAO=metalLight && [NSUserDefaults.standardUserDefaults boolForKey:@"performance.metal-ssao"] && ![NSProcessInfo.processInfo.arguments containsObject:@"--spu-ssao"];
    _report[@"metal_ssao_requested"]=@(metalSSAO);
    bces_ssao_depth_cleanup_set_enabled(![NSProcessInfo.processInfo.arguments containsObject:@"--ssao-depth-boundary-off"]);
    bces_edge_set_enabled([NSProcessInfo.processInfo.arguments containsObject:@"--edge-arm64"]);
    bces_edge_flow_enable([NSProcessInfo.processInfo.arguments containsObject:@"--diagnose-edge-flow"]);
    bces_skinning_capture_enable([NSProcessInfo.processInfo.arguments containsObject:@"--capture-skinning"]);
    _report[@"edge_flow_instrumentation_requested"]=@([NSProcessInfo.processInfo.arguments containsObject:@"--diagnose-edge-flow"]);
    unsetenv("PS3RECOMP_ENG_GPU_LIGHT_NOWB"); setenv("PS3RECOMP_ENG_GPU_SSAO", metalSSAO ? "1" : "", 1); setenv("PS3RECOMP_ENG_SKIP_FP", "", 1);
    bces_spu_copy_set_enabled([NSProcessInfo.processInfo.arguments containsObject:@"--spu-copy-on"] && ![NSProcessInfo.processInfo.arguments containsObject:@"--spu-copy-off"]);
    unsetenv("HEADLESS"); unsetenv("PS3RECOMP_METAL_HEADLESS");
    // A sensor-only joystick otherwise occupies PS3 port 0 ahead of DualSense.
    SDL_SetHint(SDL_HINT_ACCELEROMETER_AS_JOYSTICK, "0");
    SDL_SetMainReady();
    int sdl = SDL_InitSubSystem(SDL_INIT_AUDIO | SDL_INIT_GAMECONTROLLER);
    fprintf(stderr, "[bces-ios] SDL input/audio init=%d error=%s\n", sdl, SDL_GetError());
    fprintf(stderr, "[bces-ios] SDL joysticks=%d\n", SDL_NumJoysticks());
    for (int i = 0; i < SDL_NumJoysticks(); ++i)
        fprintf(stderr, "[bces-ios] joystick[%d]=%s mapped=%d\n", i, SDL_JoystickNameForIndex(i) ?: "?", SDL_IsGameController(i));
    if ([NSProcessInfo.processInfo.arguments containsObject:@"--profile-pipelines"])
        game_telemetry_pipeline_log([_documents URLByAppendingPathComponent:@"pipeline-events.csv"].path.fileSystemRepresentation);
    bces_ios_set_active(1);
    pthread_attr_t attr; pthread_attr_init(&attr);
    int rc = pthread_attr_setstacksize(&attr, 64u * 1024 * 1024); pthread_t worker;
    void* payload = (__bridge_retained void*)self;
    if (!rc) rc = pthread_create(&worker, &attr, gameWorker, payload);
    pthread_attr_destroy(&attr);
    if (rc) {
        GameController* unused = (__bridge_transfer GameController*)payload; (void)unused;
        rsx_metal_backend_attach_ios_layer(nullptr); _status.text = @"Oyun iş parçacığı başlatılamadı."; return;
    }
    pthread_detach(worker); _booted = YES; _ticks = 0; _setup.hidden = YES; _hud.hidden = YES;
    _report[@"game_booted"] = @YES; [self writeReport];
}
- (void)deactivate {
    if (!_booted) return;
    bces_ios_set_active(0);
    _report[@"renderer_pause_acknowledged"] = @(bces_ios_wait_renderer_idle(1000));
    // This closes GPU admission. It is not an all-PPU/SPU cooperative pause.
    _report[@"all_guest_threads_cooperatively_paused"] = @NO; [self writeReport];
}
- (void)activate { if (_booted) bces_ios_set_active(1); }
- (void)tick {
    bces_ssao_depth_control_poll();
    bces_edge_control_poll();
    bces_edge_flush_capture(_documents.path.fileSystemRepresentation);
    bces_skinning_capture_flush(_documents.path.fileSystemRepresentation);
    _report[@"skinning_captures"]=@(bces_skinning_capture_count());
    _report[@"culling_captures"]=@(bces_geometry_capture_count(1));
    _report[@"geometry_capture_enabled"]=@(bces_geometry_capture_enabled());
    _report[@"lighting_validation_completed"] = @(bces_light_validation_completed());
    _report[@"lighting_validation_zero_outputs_rejected"]=@(bces_light_validation_rejected_zero_output());
    _report[@"lighting_mode"] = [_report[@"metal_lighting_requested"] boolValue] ? @"experimental Metal lighting; guarded SPU fallback; SPU SSAO" : @"SPU reference";
    _report[@"metal_lighting_faults"]=@(bces_light_fault_count());
    BCESLightFarStats lightFar=bces_light_far_stats();
    _report[@"light_far"]=@{@"enabled":@(lightFar.enabled),@"reference":@(lightFar.reference),@"fast":@(lightFar.fast),@"faults":@(lightFar.faults)};
    _report[@"metal_lighting_passes"]=@(bces_light_rendered_passes());
    _report[@"metal_lighting_bindings"]=@(bces_light_bindings());
    _report[@"metal_lighting_skipped_tiles"]=@(bces_light_skipped_tiles());
    _report[@"metal_lighting_fallback_jobs"]=@(bces_light_fallback_jobs());
    bces_ssao_flush_capture(_documents.path.fileSystemRepresentation);
    _report[@"metal_ssao_last_rejection"]=@(bces_ssao_rejection());
    _report[@"metal_ssao_passes"]=@(bces_ssao_passes());
    _report[@"metal_ssao_bindings"]=@(bces_ssao_bindings());
    _report[@"metal_ssao_faults"]=@(bces_ssao_faults());
    _report[@"metal_ssao_fallback_jobs"]=@(bces_ssao_fallbacks());
    _report[@"metal_ssao_skipped_tiles"]=@(bces_ssao_skipped_tiles());
    _report[@"ssao_depth_cleanup_enabled"]=@(bces_ssao_depth_cleanup_enabled());
    _report[@"ssao_depth_original_calls"]=@(bces_ssao_depth_calls());
    _report[@"ssao_depth_boundary_blocks"]=@(bces_ssao_depth_boundaries());
    _report[@"edge_arm64_enabled"]=@(bces_edge_enabled());
    _report[@"edge_arm64_d808_calls"]=@(bces_edge_calls(0));
    _report[@"edge_arm64_d8a8_calls"]=@(bces_edge_calls(1));
    _report[@"edge_arm64_da28_calls"]=@(bces_edge_calls(2));
    _report[@"edge_arm64_validations"]=@(bces_edge_validations());
    _report[@"edge_arm64_mismatches"]=@(bces_edge_mismatches());
    if([_report[@"metal_ssao_requested"] boolValue])_report[@"lighting_mode"]=@"experimental Metal lighting + guarded Metal SSAO; original SPU half-depth retained";
    bces_frame_trace_poll();
    _report[@"frame_trace_state"] = @(bces_frame_trace_state());
    bces_cpu_profile_poll();
    _report[@"cpu_profile_state"] = @(bces_cpu_profile_state());
    NSMutableArray* controllers = [NSMutableArray new];
    BOOL pressed = NO;
    for (GCController* controller in GCController.controllers) {
        [controllers addObject:controller.vendorName ?: @"unknown"];
        GCExtendedGamepad* pad = controller.extendedGamepad;
        pressed |= pad.buttonA.isPressed || pad.buttonB.isPressed || pad.buttonX.isPressed || pad.buttonY.isPressed || pad.buttonMenu.isPressed;
    }
    _report[@"controllers"] = controllers;
    _report[@"controller_button_seen"] = @([_report[@"controller_button_seen"] boolValue] || pressed);
    task_vm_info_data_t info = {}; mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) == KERN_SUCCESS) {
        _report[@"physical_footprint"] = @(info.phys_footprint); _report[@"resident_bytes"] = @(info.resident_size);
        _report[@"virtual_bytes"] = @(info.virtual_size);
    }
    unsigned frames = ppu_boot_frames_presented(); RSXSurfaceStats stats = rsx_metal_backend_ios_stats();
    _report[@"guest_present_calls"] = @(frames); _report[@"Metal_submitted"] = @(stats.submitted);
    _report[@"Metal_completed"] = @(stats.completed); _report[@"Metal_presented"] = @(stats.presented); _report[@"Metal_errors"] = @(stats.errors);
    // Explicit development-only live A/B control; normal launches do no reads.
    if ([NSProcessInfo.processInfo.arguments containsObject:@"--spu-copy-control"]) {
        NSString* state = [NSString stringWithContentsOfURL:[_documents URLByAppendingPathComponent:@"spu-copy-control.txt"] encoding:NSUTF8StringEncoding error:nil];
        state = [state stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
        if ([state isEqualToString:@"on"]) bces_spu_copy_set_enabled(1);
        else if ([state isEqualToString:@"off"]) bces_spu_copy_set_enabled(0);
    }
    [self geometryControl];
    _report[@"renderer_memo"]=@{@"vertex":RendererMemoReport(BCES_MEMO_VERTEX),@"texture":RendererMemoReport(BCES_MEMO_TEXTURE)};
#if BCES_GBUFFER_FENCE
    _report[@"gbuffer_fence"]=@{@"mode":@(bces_gbuffer_fence_mode()),
        @"reused":@(bces_gbuffer_fence_reused()), @"rejected":@(bces_gbuffer_fence_rejected()),
        @"validated":@(bces_gbuffer_fence_validated()), @"mismatches":@(bces_gbuffer_fence_mismatches())};
#endif
    _report[@"compact_vertex"]=@{@"mode":@(bces_compact_vertex_mode()),
        @"draws":@(bces_compact_vertex_draws()), @"bytes_saved":@(bces_compact_vertex_bytes_saved())};
    BCESDispatchStats dispatchStats=bces_spu_dispatch_stats();
    uint64_t dmaStats[4];bces_dma_poison_totals(dmaStats);
    uint64_t mfcStats[3];bces_mfc_hint_stats(mfcStats);
    uint64_t mfcLayout[8];bces_mfc_layout(mfcLayout);
    _report[@"mfc_layout"]=@{@"aligned128":@(mfcLayout[0]),@"slot_bytes":@(mfcLayout[1]),@"slot_alignment":@(mfcLayout[2]),@"base_mod128":@(mfcLayout[3]),@"stride_bytes":@(mfcLayout[4]),@"engine_offset":@(mfcLayout[5]),@"table_bytes":@(mfcLayout[6]),@"engine_bytes":@(mfcLayout[7])};
    uint64_t channelStats[11];bces_channel_stats(channelStats);NSMutableArray* channelCounts=[NSMutableArray new];for(unsigned i=0;i<9;i++)[channelCounts addObject:@(channelStats[i])];
    _report[@"channel_inline"]=@{@"compiled":@(bces_channel_compiled),@"mode":@(bces_channel_get()),@"forced":@(bces_channel_forced()),@"counts":channelCounts,@"parameter_read_checks":@(channelStats[9]),@"mismatches":@(channelStats[10])};
    uint64_t overlayStats[4];bces_overlay_filter_stats(overlayStats);
    _report[@"overlay_filter"]=@{@"compiled":@(bces_overlay_filter_compiled),@"mode":@(bces_overlay_filter_get()),@"checks":@(overlayStats[0]),@"rejects":@(overlayStats[1]),@"extra_rejects":@(overlayStats[2]),@"mismatches":@(overlayStats[3])};
    _report[@"mfc_hint"]=@{@"mode":@(bces_mfc_hint_get()),@"checks":@(mfcStats[0]),@"hits":@(mfcStats[1]),@"mismatches":@(mfcStats[2]),@"storage":@"TLS-last-slot-owner-checked"};
    _report[@"dma_original_scan_build"]=@(BCES_DMA_ORIGINAL_SCAN);
    _report[@"dma_poison"]=@{@"enabled":@(bces_dma_poison_enabled()),@"forced":@(bces_dma_poison_forced()),@"sample_period":@256,@"sampled_scanned":@(dmaStats[0]),@"sampled_skipped":@(dmaStats[1]),@"sampled_bytes_scanned":@(dmaStats[2]),@"sampled_bytes_skipped":@(dmaStats[3])};
    BCESMaskStats maskStats=bces_mask_stats();
    _report[@"light_mask"]=@{@"mode":@(maskStats.enabled),@"reference":@(maskStats.reference),@"fast":@(maskStats.fast),@"faults":@(maskStats.faults),@"validations":@(maskStats.validations),@"mismatches":@(maskStats.mismatches),@"compared_tiles":@(maskStats.compared_tiles)};
    _report[@"spu_dispatch"]=@{@"enabled":@(dispatchStats.enabled),@"eligible":@(dispatchStats.eligible),@"fast":@(dispatchStats.fast),@"fallback":@(dispatchStats.fallback),@"reset_checks":@(dispatchStats.reset_checks),@"reset_bypasses":@(dispatchStats.reset_bypasses)};
    _report[@"geometry_capture_enabled"]=@(bces_geometry_capture_enabled());_report[@"geometry_capture_pending"]=@(bces_geometry_capture_pending_count());
    [_performance sample];
    _report[@"performance"] = [_performance report];
    struct stat size; if (!fstat(STDERR_FILENO, &size) && size.st_size > 16 * 1024 * 1024) {
        int fd = open("/dev/null", O_WRONLY); if (fd >= 0) { dup2(fd, STDOUT_FILENO); dup2(fd, STDERR_FILENO); close(fd); }
        _report[@"runtime_log_capped"] = @YES;
    }
    if (_booted && _duration && ++_ticks >= _duration) {
        bces_ios_set_active(0); _report[@"diagnostic_time_limit"] = @YES;
        _report[@"renderer_stop_acknowledged"] = @(bces_ios_wait_renderer_idle(1000));
        [self writeReport]; _exit(124); // Only an explicitly timed development run.
    }
    [self writeReport];
}
- (void)geometryControl {
    if(!_geometryControlEnabled)return;
    NSURL*file=[_documents URLByAppendingPathComponent:@"geometry-control.json"];
    NSData*data=[NSData dataWithContentsOfURL:file];if(!data)return;
    NSString*error=nil;NSDictionary*command=bces_geometry_parse_command(data,_geometryControlSession,&error);
    if(!command){if([error isEqualToString:@"Session does not match this process"])return;_report[@"geometry_control_error"]=error?:@"Invalid command";return;}
    NSString*token=command[@"token"];if([token isEqualToString:_geometryControlToken])return;
    if((command[@"vertex_memo"]||command[@"texture_memo"])&&![_report[@"renderer_memo_control_enabled"] boolValue]){_report[@"geometry_control_error"]=@"Renderer memo commands require --renderer-memo-control";return;}
    if (command[@"gbuffer_fence"] && ![_report[@"gbuffer_fence_control_enabled"] boolValue]) {
        _report[@"geometry_control_error"]=@"G-buffer fence commands require --gbuffer-fence-control";
        return;
    }
    if (command[@"compact_vertex"] && ![_report[@"compact_vertex_control_enabled"] boolValue]) {
        _report[@"geometry_control_error"]=@"Compact vertex requires --compact-vertex-control";
        return;
    }
    if(command[@"spu_dispatch"]&&![_report[@"spu_dispatch_control_enabled"] boolValue]){_report[@"geometry_control_error"]=@"SPU dispatch commands require --spu-dispatch-control";return;}
    if(command[@"dma_poison_skip"]&&![_report[@"dma_poison_control_enabled"] boolValue]){_report[@"geometry_control_error"]=@"DMA poison commands require --dma-poison-control";return;}
    if(command[@"mfc_hint"]&&![_report[@"mfc_hint_control_enabled"] boolValue]){_report[@"geometry_control_error"]=@"MFC hint commands require --mfc-hint-control";return;}
    if(command[@"channel_inline"]&&(![_report[@"channel_inline_control_enabled"] boolValue]||(!bces_channel_compiled&&[command[@"channel_inline"] unsignedIntValue]))){_report[@"geometry_control_error"]=@"Channel inline requires compiled variant and --channel-inline-control";return;}
    if(command[@"overlay_filter"]&&(![_report[@"overlay_filter_control_enabled"] boolValue]||(!bces_overlay_filter_compiled&&[command[@"overlay_filter"] unsignedIntValue]))){_report[@"geometry_control_error"]=@"Overlay filter requires compiled experiment and --overlay-filter-control";return;}
    if(command[@"light_mask"]&&![_report[@"light_mask_control_enabled"] boolValue]){_report[@"geometry_control_error"]=@"Light mask commands require --light-mask-control";return;}
    if(command[@"light_far"]&&![_report[@"light_far_control_enabled"] boolValue]){_report[@"geometry_control_error"]=@"Light far commands require --light-far-control";return;}
    if([command[@"capture"] boolValue]&&((command[@"skin"]&&[command[@"skin"] unsignedIntValue])||(command[@"cull"]&&[command[@"cull"] unsignedIntValue])||(!command[@"skin"]&&(bces_geometry_route(0)||bces_geometry_route(1))))){_report[@"geometry_control_error"]=@"Captures require SPU/SPU reference";return;}
    if(command[@"skin"])[_performance applyGeometrySkin:[command[@"skin"] unsignedIntValue] cull:[command[@"cull"] unsignedIntValue] validation:[command[@"validation"] boolValue]];
    if([command[@"prepare_metal"] boolValue])bces_batch_metal_prepare();
    if(command[@"capture"])bces_skinning_capture_enable([command[@"capture"] boolValue]);
    if(command[@"vertex_memo"])bces_renderer_memo_set(BCES_MEMO_VERTEX,[command[@"vertex_memo"] unsignedIntValue]);
    if(command[@"texture_memo"])bces_renderer_memo_set(BCES_MEMO_TEXTURE,[command[@"texture_memo"] unsignedIntValue]);
#if BCES_GBUFFER_FENCE
    if (command[@"gbuffer_fence"]) bces_gbuffer_fence_set([command[@"gbuffer_fence"] unsignedIntValue]);
#endif
    if (command[@"compact_vertex"]) bces_compact_vertex_set([command[@"compact_vertex"] unsignedIntValue]);
    if(command[@"spu_dispatch"])bces_spu_dispatch_set([command[@"spu_dispatch"] unsignedIntValue],1);
    if(command[@"dma_poison_skip"])bces_dma_poison_set([command[@"dma_poison_skip"] unsignedIntValue]);
    if(command[@"mfc_hint"])bces_mfc_hint_set([command[@"mfc_hint"] unsignedIntValue]);
    if(command[@"channel_inline"])bces_channel_set([command[@"channel_inline"] unsignedIntValue]);
    if(command[@"overlay_filter"])bces_overlay_filter_set([command[@"overlay_filter"] unsignedIntValue]);
    if(command[@"light_mask"])bces_mask_set([command[@"light_mask"] unsignedIntValue]);
    if(command[@"light_far"])bces_light_far_set([command[@"light_far"] unsignedIntValue]);
    if(command[@"frames_since"]){
        auto events=std::make_unique<GameFrameEvent[]>(8192);uint64_t dropped=0;
        unsigned count=game_telemetry_frame_events([command[@"frames_since"] unsignedLongLongValue],events.get(),8192,&dropped);
        NSString*name=[NSString stringWithFormat:@"geometry-frames-%@.csv",token];NSMutableString*csv=[NSMutableString stringWithString:@"sequence,monotonic_s\n"];
        for(unsigned i=0;i<count;i++)[csv appendFormat:@"%llu,%.9f\n",events[i].sequence,events[i].seconds];
        NSError*writeError=nil;BOOL written=[csv writeToURL:[_documents URLByAppendingPathComponent:name] atomically:YES encoding:NSUTF8StringEncoding error:&writeError];
        if(!written){_report[@"geometry_control_error"]=writeError.description?:@"Frame export failed";return;}
        _report[@"geometry_frame_export"]=@{@"token":token,@"file":name,@"rows":@(count),@"dropped":@(dropped),@"first":@(count?events[0].sequence:0),@"last":@(count?events[count-1].sequence:0)};
    }
    _geometryControlToken=token;[_report removeObjectForKey:@"geometry_control_error"];
    _report[@"geometry_control_ack"]=token;_report[@"geometry_control_applied_s"]=@(CACurrentMediaTime());_report[@"geometry_control_revision"]=@(bces_geometry_revision());
}
- (void)writeReport {
    NSData* data = [NSJSONSerialization dataWithJSONObject:_report options:NSJSONWritingPrettyPrinted error:nil];
    [data writeToURL:_reportURL options:NSDataWritingAtomic error:nil];
}
@end
@interface GameAppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation GameAppDelegate
@end
@interface GameSceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic, strong) UIWindow* window;
@end
@implementation GameSceneDelegate
- (void)scene:(UIScene*)scene willConnectToSession:(UISceneSession*)session options:(UISceneConnectionOptions*)options {
    (void)session; (void)options;
    if (![scene isKindOfClass:UIWindowScene.class]) return;
    self.window = [[UIWindow alloc] initWithWindowScene:(UIWindowScene*)scene];
    self.window.rootViewController = [GameController new]; [self.window makeKeyAndVisible];
}
@end
int main(int argc, char** argv) { @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(GameAppDelegate.class)); } }
