#include "HostStack.h"
#include "RSXLegacyFastPath.h"
#import "GamePerformance.h"
#import <QuartzCore/QuartzCore.h>
#import <Metal/Metal.h>
#include "GameTelemetry.h"
#include "GeometryKernels.h"
#include "GeometryMetalBatches.h"
#include "BCESSpuCopy.h"
#include "RSXMetalSurface.h"
#include <mach/mach.h>
#include <os/proc.h>
#include <sys/resource.h>
#include <cmath>

static NSArray<NSString*>* Keys() { return @[@"fps",@"frame",@"cpu",@"gpu",@"memory",@"thermal",@"queue",@"render",@"headroom",@"geometry",@"rsx"]; }
static NSArray<NSString*>* Titles() { return @[@"FPS",@"Frame time · mean / 95th percentile",@"CPU usage",@"GPU command time",@"Memory · current / peak",@"Thermal state and battery",@"Metal queue and errors",@"Render loop time",@"Memory headroom",@"Geometry experiments and validation",@"RSX command path"]; }
static NSString* Key(NSString* name) { return [@"performance." stringByAppendingString:name]; }
// Pair order is always skinning / culling. Individual switches also retain
// SPU/ARM64 and SPU/Metal combinations outside these common presets.
static const unsigned GeometryPresets[5][2]={{0,0},{1,2},{2,1},{1,1},{2,2}};
static unsigned GeometryChoice(NSUserDefaults* d,unsigned kind) {
    NSString* prefix=kind?@"cull":@"skin";
    return [d boolForKey:Key([prefix stringByAppendingString:@"-metal"])]?2:[d boolForKey:Key([prefix stringByAppendingString:@"-arm64"])]?1:0;
}
static NSString* GeometryPair(unsigned skin,unsigned cull) {
    NSArray* names=@[@"SPU",@"ARM64",@"Metal"];
    return [NSString stringWithFormat:@"%@ / %@",names[MIN(skin,2u)],names[MIN(cull,2u)]];
}
static NSString* Thermal() {
    switch (NSProcessInfo.processInfo.thermalState) {
        case NSProcessInfoThermalStateNominal:return @"Nominal";
        case NSProcessInfoThermalStateFair:return @"Fair";
        case NSProcessInfoThermalStateSerious:return @"Serious";
        default:return @"Critical";
    }
}
@class PerformanceSettings;
@interface GamePerformance ()
- (void)changed;
- (void)exportCSV;
@end
@interface PerformanceSettings : UITableViewController
@property(nonatomic, weak) GamePerformance* owner;
@end
@implementation GamePerformance {
    __weak UIViewController* _controller;
    NSURL* _documents;
    UILabel* _label;
    UIButton* _button;
    NSLayoutConstraint* _left;
    NSLayoutConstraint* _right;
    NSMutableDictionary* _values;
    double _previousTime, _previousCPU;
    uint64_t _peak;
    NSFileHandle* _csv;
    NSUInteger _csvBytes;
    NSUInteger _memoryWarnings;
    id<MTLDevice> _device;
}
- (instancetype)initWithController:(UIViewController*)controller documents:(NSURL*)documents {
    if (!(self=[super init])) return nil;
    _device=MTLCreateSystemDefaultDevice();
    _controller=controller; _documents=documents; _values=[NSMutableDictionary new];
    [NSUserDefaults.standardUserDefaults registerDefaults:@{Key(@"verified-fast-paths"):@YES,Key(@"visible"):@YES,Key(@"fps"):@YES,Key(@"frame"):@YES,Key(@"cpu"):@YES,Key(@"gpu"):@YES,Key(@"memory"):@YES,Key(@"thermal"):@YES,Key(@"awake"):@YES,Key(@"metal-lighting"):@YES,Key(@"metal-ssao"):@YES,Key(@"geometry-validation"):@YES,Key(@"geometry"):@YES,Key(@"rsx"):@YES,Key(@"rsx-legacy-fast"):@YES}];
    [NSNotificationCenter.defaultCenter addObserver:self selector:@selector(memoryWarning) name:UIApplicationDidReceiveMemoryWarningNotification object:nil];
    UIDevice.currentDevice.batteryMonitoringEnabled=YES;
    _label=[UILabel new]; _label.translatesAutoresizingMaskIntoConstraints=NO;
    _label.textColor=UIColor.whiteColor; _label.backgroundColor=[UIColor colorWithWhite:0 alpha:0.7]; _label.numberOfLines=0;
    _label.userInteractionEnabled=NO; _label.accessibilityIdentifier=@"performanceHUD";
    [controller.view addSubview:_label];
    _button=[UIButton buttonWithType:UIButtonTypeSystem]; _button.translatesAutoresizingMaskIntoConstraints=NO;
    [_button setImage:[UIImage systemImageNamed:@"ellipsis.circle.fill"] forState:UIControlStateNormal];
    _button.tintColor=UIColor.whiteColor; _button.backgroundColor=[UIColor colorWithWhite:0 alpha:.65]; _button.layer.cornerRadius=22;
    _button.accessibilityLabel=@"Game Settings"; _button.accessibilityIdentifier=@"gameSettings";
    [_button addTarget:self action:@selector(openSettings) forControlEvents:UIControlEventTouchUpInside];
    [controller.view addSubview:_button];
    UILayoutGuide* safe=controller.view.safeAreaLayoutGuide;
    _left=[_label.leadingAnchor constraintEqualToAnchor:safe.leadingAnchor constant:8];
    _right=[_label.trailingAnchor constraintEqualToAnchor:_button.leadingAnchor constant:-8];
    [NSLayoutConstraint activateConstraints:@[
      [_button.trailingAnchor constraintEqualToAnchor:safe.trailingAnchor constant:-8],[_button.topAnchor constraintEqualToAnchor:safe.topAnchor constant:8],
      [_button.widthAnchor constraintEqualToConstant:44],[_button.heightAnchor constraintEqualToConstant:44],
      [_label.topAnchor constraintEqualToAnchor:safe.topAnchor constant:8],[_label.widthAnchor constraintLessThanOrEqualToAnchor:safe.widthAnchor multiplier:.6]]];
    [self changed]; return self;
}
- (void)memoryWarning { ++_memoryWarnings; }
- (void)dealloc { [NSNotificationCenter.defaultCenter removeObserver:self]; }
- (void)changed {
    NSUserDefaults* d=NSUserDefaults.standardUserDefaults;
    BOOL right=[d boolForKey:Key(@"right")]; _left.active=NO; _right.active=NO; if(right)_right.active=YES;else _left.active=YES;
    _label.font=[UIFont monospacedSystemFontOfSize:[d boolForKey:Key(@"large")]?14:11 weight:UIFontWeightMedium];
    UIApplication.sharedApplication.idleTimerDisabled=[d boolForKey:Key(@"awake")];
    if (![d boolForKey:Key(@"csv")]) { [_csv closeFile]; _csv=nil; }
    bces_geometry_set_routes(GeometryChoice(d,0),GeometryChoice(d,1));
    bces_geometry_set_validation([d boolForKey:Key(@"geometry-validation")]);
    [self updateHUD];
}
- (void)applyGeometrySkin:(unsigned)skin cull:(unsigned)cull validation:(BOOL)validation {
    if(skin>=3||cull>=3)return;NSUserDefaults*d=NSUserDefaults.standardUserDefaults;
    for(unsigned kind=0;kind<2;kind++){unsigned route=kind?cull:skin;NSString*prefix=kind?@"cull":@"skin";
        [d setBool:route==1 forKey:Key([prefix stringByAppendingString:@"-arm64"])];[d setBool:route==2 forKey:Key([prefix stringByAppendingString:@"-metal"])];}
    [d setBool:validation forKey:Key(@"geometry-validation")];[self changed];
}
- (void)openSettings {
    if (_controller.presentedViewController) return;
    PerformanceSettings* settings=[[PerformanceSettings alloc] initWithStyle:UITableViewStyleInsetGrouped]; settings.owner=self;
    settings.title=@"Game Settings";
    settings.navigationItem.rightBarButtonItem=[[UIBarButtonItem alloc] initWithTitle:@"Done" style:UIBarButtonItemStyleDone target:settings action:@selector(close)];
    UINavigationController* nav=[[UINavigationController alloc] initWithRootViewController:settings];
    // Avoid the sheet shadow bitmap allocation path seen in device crashes.
    // OverFullScreen keeps the game view/layer attached beneath the panel.
    nav.modalPresentationStyle=UIModalPresentationOverFullScreen;
    [_controller presentViewController:nav animated:YES completion:nil];
}
- (void)sample {
    double now=CACurrentMediaTime(); GameTelemetrySnapshot s=game_telemetry_snapshot(now);
    struct rusage usage={}; double cpu=0; BOOL cpuOK=getrusage(RUSAGE_SELF,&usage)==0;
    if(cpuOK)cpu=usage.ru_utime.tv_sec+usage.ru_utime.tv_usec/1e6+usage.ru_stime.tv_sec+usage.ru_stime.tv_usec/1e6;
    BOOL cpuValid=cpuOK && _previousTime>0 && now>_previousTime && cpu>=_previousCPU;
    double percent=cpuValid?100*(cpu-_previousCPU)/(now-_previousTime):0;
    _previousTime=now; _previousCPU=cpu;
    task_vm_info_data_t vm={}; mach_msg_type_number_t count=TASK_VM_INFO_COUNT;
    BOOL memoryOK=task_info(mach_task_self(),TASK_VM_INFO,(task_info_t)&vm,&count)==KERN_SUCCESS;
    if(memoryOK)_peak=MAX(_peak,vm.phys_footprint);
    // Advisory per-process allocation headroom, not device-wide free RAM.
    size_t headroom=os_proc_available_memory();
    RSXSurfaceStats metal=rsx_metal_backend_ios_stats();
    BCESSpuCopyStats copy=bces_spu_copy_stats();
    BCESHostStackStats stacks=bces_host_stack_sample();
    _values=[@{@"sample_monotonic_seconds":@(now),@"fps":@(s.fps),@"frame_mean_ms":@(s.frame_mean_ms),@"frame_p95_ms":@(s.frame_p95_ms),
      @"frame_samples":@(s.frame_intervals),@"present_total":@(s.present_total),@"present_time":@(s.present_time),@"present_sample_time":@(s.sample_time),@"low_power_mode":@(NSProcessInfo.processInfo.lowPowerModeEnabled),@"application_active":@(UIApplication.sharedApplication.applicationState==UIApplicationStateActive),@"settings_panel_open":@(_controller.presentedViewController!=nil),@"gpu_mean_ms":@(s.gpu_mean_ms),@"gpu_samples":@(s.gpu_samples),
      @"render_mean_ms":@(s.render_mean_ms),@"render_samples":@(s.render_samples),@"cpu_percent":@(percent),@"cpu_valid":@(cpuValid),
      @"virtual_size_bytes":@(vm.virtual_size),@"physical_footprint":@(vm.phys_footprint),@"peak_sampled_footprint":@(_peak),@"memory_valid":@(memoryOK),@"available_process_memory_bytes":@(headroom),@"memory_warning_count":@(_memoryWarnings),@"metal_allocated_bytes":@(_device.currentAllocatedSize),@"metal_recommended_working_set_bytes":@(_device.recommendedMaxWorkingSetSize),@"pipeline_started":@(s.pipeline_started),@"pipeline_finished":@(s.pipeline_finished),@"pipeline_failed":@(s.pipeline_failed),
      @"spu_copy_enabled":@(copy.enabled),@"spu_copy_fast_calls":@(copy.fast_calls),@"spu_copy_fallback_calls":@(copy.fallback_calls),@"spu_copy_bytes":@(copy.copied_bytes),
      @"thermal_state":@(NSProcessInfo.processInfo.thermalState),@"battery_level":@(UIDevice.currentDevice.batteryLevel),
      @"metal_in_flight":@(metal.submitted>metal.completed+metal.errors?metal.submitted-metal.completed-metal.errors:0),@"metal_errors":@(metal.errors)} mutableCopy];
    BCESRSXLegacyStats rsx=bces_rsx_legacy_stats();
    _values[@"rsx_legacy_configured"]=@(rsx.configured);_values[@"rsx_legacy_requested"]=@(rsx.requested);
    _values[@"rsx_legacy_enabled"]=@(rsx.enabled);_values[@"rsx_legacy_debug_fallback"]=@(rsx.debug_fallback);
    _values[@"rsx_legacy_methods"]=@(rsx.methods);_values[@"rsx_legacy_state_skipped"]=@(rsx.state_skipped);
    _values[@"rsx_legacy_forwarded"]=@(rsx.legacy_forwarded);_values[@"rsx_legacy_sync_forwarded"]=@(rsx.sync_forwarded);
    _values[@"rsx_legacy_draw_forwarded"]=@(rsx.draw_forwarded);
    _values[@"host_stacks"] = @{@"reserved_bytes":@(stacks.reserved_bytes),@"peak_sampled_used_bytes":@(stacks.peak_sampled_used_bytes),@"minimum_sampled_margin_bytes":@(stacks.minimum_sampled_margin_bytes),@"registered":@(stacks.registered),@"sampled":@(stacks.sampled)};
    for(unsigned kind=0;kind<2;kind++){
        BCESGeometryStats g=bces_geometry_stats(kind);NSString* prefix=kind?@"cull":@"skin";
        _values[[prefix stringByAppendingString:@"_route"]]=@(g.requested_route);
        _values[[prefix stringByAppendingString:@"_blocked"]]=@(g.blocked_mask);
        _values[[prefix stringByAppendingString:@"_calls"]]=@(g.calls[1]+g.calls[2]);
        _values[[prefix stringByAppendingString:@"_fallbacks"]]=@(g.fallbacks);
        _values[[prefix stringByAppendingString:@"_validations"]]=@(g.validations);
        _values[[prefix stringByAppendingString:@"_mismatches"]]=@(g.mismatches);
        _values[[prefix stringByAppendingString:@"_failures"]]=@(g.failures);
        _values[[prefix stringByAppendingString:@"_trial_ms"]]=@(g.trial_ns/1e6);
        _values[[prefix stringByAppendingString:@"_gpu_ms"]]=@(g.gpu_ns/1e6);
        _values[[prefix stringByAppendingString:@"_reference_ms"]]=@(g.reference_ns/1e6);
        _values[[prefix stringByAppendingString:@"_sampled_calls"]]=@(g.sampled_calls);
        _values[[prefix stringByAppendingString:@"_batch_candidates"]]=@(g.batch_candidates);
        _values[[prefix stringByAppendingString:@"_gpu_batches"]]=@(g.gpu_batches);
        _values[[prefix stringByAppendingString:@"_calibration_batches"]]=@(g.calibration_batches);
        _values[[prefix stringByAppendingString:@"_cpu_small_batches"]]=@(g.cpu_small_batches);
        _values[[prefix stringByAppendingString:@"_cpu_busy_batches"]]=@(g.cpu_busy_batches);
        _values[[prefix stringByAppendingString:@"_cpu_dependency_batches"]]=@(g.cpu_dependency_batches);
        _values[[prefix stringByAppendingString:@"_cpu_cost_rejected_batches"]]=@(g.cpu_cost_rejected_batches);
        _values[[prefix stringByAppendingString:@"_cpu_only_calls"]]=@(g.cpu_only_calls);
        _values[[prefix stringByAppendingString:@"_unsupported_calls"]]=@(g.unsupported_calls);
        _values[[prefix stringByAppendingString:@"_admitted_mask"]]=@(g.admitted_mask);
        _values[[prefix stringByAppendingString:@"_rejected_mask"]]=@(g.rejected_mask);
        _values[[prefix stringByAppendingString:@"_calibrating"]]=@(g.calibrating);
        _values[[prefix stringByAppendingString:@"_input_bytes"]]=@(g.input_bytes);
        _values[[prefix stringByAppendingString:@"_output_bytes"]]=@(g.output_bytes);
        _values[[prefix stringByAppendingString:@"_copy_ms"]]=@(g.copy_ns/1e6);
        _values[[prefix stringByAppendingString:@"_execute_ms"]]=@(g.execute_ns/1e6);
        _values[[prefix stringByAppendingString:@"_commit_ms"]]=@(g.commit_ns/1e6);
        _values[[prefix stringByAppendingString:@"_input_ms"]]=@(g.input_ns/1e6);
        _values[[prefix stringByAppendingString:@"_submit_ms"]]=@(g.submit_ns/1e6);
        _values[[prefix stringByAppendingString:@"_wait_ms"]]=@(g.wait_ns/1e6);
        _values[[prefix stringByAppendingString:@"_output_ms"]]=@(g.output_ns/1e6);
        _values[[prefix stringByAppendingString:@"_entry_count"]]=@(g.entries[g.requested_route]);
        _values[[prefix stringByAppendingString:@"_total_ms"]]=@(g.total_ns[g.requested_route]/1e6);
        _values[[prefix stringByAppendingString:@"_all_entries"]]=@[@(g.entries[0]),@(g.entries[1]),@(g.entries[2])];
        _values[[prefix stringByAppendingString:@"_all_total_ms"]]=@[@(g.total_ns[0]/1e6),@(g.total_ns[1]/1e6),@(g.total_ns[2]/1e6)];
        NSMutableArray* gates=[NSMutableArray new];for(unsigned i=0;i<21;i++){BCESGeometryGateStats gate=bces_geometry_gate_stats(kind,i);if(gate.state||gate.samples)[gates addObject:@{@"pc":@(gate.pc),@"size_bucket":@(gate.bucket),@"state":@(gate.state),@"samples":@(gate.samples),@"cpu_ms":@(gate.cpu_ns/1e6),@"gpu_total_ms":@(gate.gpu_ns/1e6)}];}
        _values[[prefix stringByAppendingString:@"_gates"]]=gates;
    }
    _values[@"geometry_pair"]=GeometryPair(bces_geometry_route(0),bces_geometry_route(1));
    _values[@"geometry_metal_state"]=@(bces_geometry_metal_state());
    _values[@"geometry_validation_all"]=@(bces_geometry_validation_enabled());
    _values[@"geometry_revision"]=@(bces_geometry_revision());_values[@"geometry_timer_version"]=@2;_values[@"geometry_component_sample_period"]=@64;
    _values[@"geometry_native_math"]=@(bces_batch_native_math_enabled());_values[@"geometry_compile_stage"]=@(bces_batch_metal_compile_stage());
    [self updateHUD]; [self recordCSV];
}
- (NSDictionary*)report { return [_values copy]; }
- (void)updateHUD {
    NSUserDefaults* d=NSUserDefaults.standardUserDefaults; NSMutableArray* lines=[NSMutableArray new];
    if([d boolForKey:Key(@"fps")])[lines addObject:[NSString stringWithFormat:@" FPS  %.1f ",[_values[@"fps"] doubleValue]]];
    if([d boolForKey:Key(@"frame")])[lines addObject:[_values[@"frame_samples"] unsignedIntValue]?[NSString stringWithFormat:@" Frame %.1f / %.1f ms ",[_values[@"frame_mean_ms"] doubleValue],[_values[@"frame_p95_ms"] doubleValue]]:@" Frame — "];
    if([d boolForKey:Key(@"cpu")])[lines addObject:[_values[@"cpu_valid"] boolValue]?[NSString stringWithFormat:@" CPU  %.0f%% ",[_values[@"cpu_percent"] doubleValue]]:@" CPU  — "];
    if([d boolForKey:Key(@"gpu")])[lines addObject:[_values[@"gpu_samples"] unsignedIntValue]?[NSString stringWithFormat:@" GPU  %.2f ms ",[_values[@"gpu_mean_ms"] doubleValue]]:@" GPU  — "];
    if([d boolForKey:Key(@"memory")])[lines addObject:[NSString stringWithFormat:@" RAM  %.0f / %.0f MiB ",[_values[@"physical_footprint"] doubleValue]/1048576,[_values[@"peak_sampled_footprint"] doubleValue]/1048576]];
    if([d boolForKey:Key(@"headroom")])[lines addObject:[NSString stringWithFormat:@" Headroom %.0f MiB · Warnings %@ ",[_values[@"available_process_memory_bytes"] doubleValue]/1048576,_values[@"memory_warning_count"]?:@0]];
    if([d boolForKey:Key(@"thermal")]) { float battery=UIDevice.currentDevice.batteryLevel;
      [lines addObject:[NSString stringWithFormat:@" %@ · %@%@ ",Thermal(),battery>=0?[NSString stringWithFormat:@"Battery %.0f%%",battery*100]:@"Battery —",NSProcessInfo.processInfo.lowPowerModeEnabled?@" · Low Power":@""]]; }
    if([d boolForKey:Key(@"queue")])[lines addObject:[NSString stringWithFormat:@" Queue %@ · Errors %@ ",_values[@"metal_in_flight"]?:@0,_values[@"metal_errors"]?:@0]];
    if([d boolForKey:Key(@"render")])[lines addObject:[NSString stringWithFormat:@" Render loop %.1f ms ",[_values[@"render_mean_ms"] doubleValue]]];
    if([d boolForKey:Key(@"geometry")])for(NSString* prefix in @[@"skin",@"cull"]){
        unsigned route=[_values[[prefix stringByAppendingString:@"_route"]] unsignedIntValue];
        if(route==2&&bces_geometry_metal_state()!=2)[lines addObject:bces_geometry_metal_state()==3?@" Geometry Metal unavailable · SPU ":@" Geometry Metal preparing · SPU "];
        if(route==2)[lines addObject:[NSString stringWithFormat:@" %@ GPU %@ · CPU fallback %@ · calibration %@ ",prefix,_values[[prefix stringByAppendingString:@"_gpu_batches"]]?:@0,_values[[prefix stringByAppendingString:@"_cpu_cost_rejected_batches"]]?:@0,_values[[prefix stringByAppendingString:@"_calibration_batches"]]?:@0]];
        if(route)[lines addObject:[NSString stringWithFormat:@" %@ %@ · validated %@ · errors %@/%@ %@ ",prefix,@[@"SPU",@"ARM64",@"Metal"][MIN(route,2u)],_values[[prefix stringByAppendingString:@"_validations"]]?:@0,_values[[prefix stringByAppendingString:@"_mismatches"]]?:@0,_values[[prefix stringByAppendingString:@"_failures"]]?:@0,[_values[[prefix stringByAppendingString:@"_blocked"]] unsignedIntValue]?@"BLOCKED":@""]];
    }
    if([d boolForKey:Key(@"rsx")]){
        NSString* mode=![_values[@"rsx_legacy_configured"] boolValue]?@"—":[_values[@"rsx_legacy_debug_fallback"] boolValue]?@"diagnostic / full path":[_values[@"rsx_legacy_state_skipped"] unsignedLongLongValue]?@"fast":[_values[@"rsx_legacy_enabled"] boolValue]?@"ready":@"original";
        [lines addObject:[NSString stringWithFormat:@" RSX %@ · skipped %@ ",mode,_values[@"rsx_legacy_state_skipped"]?:@0]];
    }
    _label.text=[lines componentsJoinedByString:@"\n"]; _label.hidden=![d boolForKey:Key(@"visible")] || !lines.count;
}
- (void)recordCSV {
    if(![NSUserDefaults.standardUserDefaults boolForKey:Key(@"csv")])return;
    if(!_csv) {
        NSURL* path=[_documents URLByAppendingPathComponent:@"performance.csv"];
        NSURL* previous=[_documents URLByAppendingPathComponent:@"performance-previous.csv"];
        if([NSFileManager.defaultManager fileExistsAtPath:path.path]) { [NSFileManager.defaultManager removeItemAtURL:previous error:nil]; [NSFileManager.defaultManager moveItemAtURL:path toURL:previous error:nil]; }
        NSData* header=[@"monotonic_s,fps,frame_mean_ms,frame_p95_ms,cpu_percent,gpu_mean_ms,render_mean_ms,footprint_bytes,peak_sampled_bytes,thermal,battery,metal_errors,frame_samples,gpu_samples,render_samples,cpu_valid,memory_valid,available_process_memory_bytes,memory_warning_count,metal_allocated_bytes,pipeline_started,pipeline_finished,pipeline_failed,spu_copy_enabled,spu_copy_fast_calls,spu_copy_fallback_calls,spu_copy_bytes,skin_route,cull_route,geometry_validation_all,skin_blocked,skin_calls,skin_fallbacks,skin_validations,skin_mismatches,skin_failures,skin_trial_ms,skin_gpu_ms,skin_reference_ms,cull_blocked,cull_calls,cull_fallbacks,cull_validations,cull_mismatches,cull_failures,cull_trial_ms,cull_gpu_ms,cull_reference_ms,geometry_pair,present_total,present_time,present_sample_time,low_power_mode,application_active,settings_panel_open,geometry_revision,geometry_timer_version,geometry_compile_stage,skin_sampled_calls,skin_batch_candidates,skin_gpu_batches,skin_calibration_batches,skin_cpu_small_batches,skin_cpu_busy_batches,skin_cpu_dependency_batches,skin_cpu_cost_rejected_batches,skin_cpu_only_calls,skin_unsupported_calls,skin_admitted_mask,skin_rejected_mask,skin_calibrating,skin_input_bytes,skin_output_bytes,skin_copy_ms,skin_execute_ms,skin_commit_ms,skin_input_ms,skin_submit_ms,skin_wait_ms,skin_output_ms,skin_entry_count,skin_total_ms,cull_sampled_calls,cull_batch_candidates,cull_gpu_batches,cull_calibration_batches,cull_cpu_small_batches,cull_cpu_busy_batches,cull_cpu_dependency_batches,cull_cpu_cost_rejected_batches,cull_cpu_only_calls,cull_unsupported_calls,cull_admitted_mask,cull_rejected_mask,cull_calibrating,cull_input_bytes,cull_output_bytes,cull_copy_ms,cull_execute_ms,cull_commit_ms,cull_input_ms,cull_submit_ms,cull_wait_ms,cull_output_ms,cull_entry_count,cull_total_ms,rsx_legacy_configured,rsx_legacy_requested,rsx_legacy_enabled,rsx_legacy_debug_fallback,rsx_legacy_methods,rsx_legacy_state_skipped,rsx_legacy_forwarded,rsx_legacy_sync_forwarded,rsx_legacy_draw_forwarded\n" dataUsingEncoding:NSUTF8StringEncoding];
        [header writeToURL:path atomically:YES]; _csv=[NSFileHandle fileHandleForWritingAtPath:path.path]; [_csv seekToEndOfFile]; _csvBytes=header.length;
    }
    if(!_csv || _csvBytes>=5*1024*1024)return;
    NSArray* keys=@[@"sample_monotonic_seconds",@"fps",@"frame_mean_ms",@"frame_p95_ms",@"cpu_percent",@"gpu_mean_ms",@"render_mean_ms",@"physical_footprint",@"peak_sampled_footprint",@"thermal_state",@"battery_level",@"metal_errors",@"frame_samples",@"gpu_samples",@"render_samples",@"cpu_valid",@"memory_valid",@"available_process_memory_bytes",@"memory_warning_count",@"metal_allocated_bytes",@"pipeline_started",@"pipeline_finished",@"pipeline_failed",@"spu_copy_enabled",@"spu_copy_fast_calls",@"spu_copy_fallback_calls",@"spu_copy_bytes",@"skin_route",@"cull_route",@"geometry_validation_all",@"skin_blocked",@"skin_calls",@"skin_fallbacks",@"skin_validations",@"skin_mismatches",@"skin_failures",@"skin_trial_ms",@"skin_gpu_ms",@"skin_reference_ms",@"cull_blocked",@"cull_calls",@"cull_fallbacks",@"cull_validations",@"cull_mismatches",@"cull_failures",@"cull_trial_ms",@"cull_gpu_ms",@"cull_reference_ms",@"geometry_pair",@"present_total",@"present_time",@"present_sample_time",@"low_power_mode",@"application_active",@"settings_panel_open",@"geometry_revision",@"geometry_timer_version",@"geometry_compile_stage",@"skin_sampled_calls",@"skin_batch_candidates",@"skin_gpu_batches",@"skin_calibration_batches",@"skin_cpu_small_batches",@"skin_cpu_busy_batches",@"skin_cpu_dependency_batches",@"skin_cpu_cost_rejected_batches",@"skin_cpu_only_calls",@"skin_unsupported_calls",@"skin_admitted_mask",@"skin_rejected_mask",@"skin_calibrating",@"skin_input_bytes",@"skin_output_bytes",@"skin_copy_ms",@"skin_execute_ms",@"skin_commit_ms",@"skin_input_ms",@"skin_submit_ms",@"skin_wait_ms",@"skin_output_ms",@"skin_entry_count",@"skin_total_ms",@"cull_sampled_calls",@"cull_batch_candidates",@"cull_gpu_batches",@"cull_calibration_batches",@"cull_cpu_small_batches",@"cull_cpu_busy_batches",@"cull_cpu_dependency_batches",@"cull_cpu_cost_rejected_batches",@"cull_cpu_only_calls",@"cull_unsupported_calls",@"cull_admitted_mask",@"cull_rejected_mask",@"cull_calibrating",@"cull_input_bytes",@"cull_output_bytes",@"cull_copy_ms",@"cull_execute_ms",@"cull_commit_ms",@"cull_input_ms",@"cull_submit_ms",@"cull_wait_ms",@"cull_output_ms",@"cull_entry_count",@"cull_total_ms",@"rsx_legacy_configured",@"rsx_legacy_requested",@"rsx_legacy_enabled",@"rsx_legacy_debug_fallback",@"rsx_legacy_methods",@"rsx_legacy_state_skipped",@"rsx_legacy_forwarded",@"rsx_legacy_sync_forwarded",@"rsx_legacy_draw_forwarded"];
    NSMutableArray* row=[NSMutableArray new]; for(NSString* key in keys)[row addObject:[_values[key] description]?:@""];
    NSData* data=[[[row componentsJoinedByString:@","] stringByAppendingString:@"\n"] dataUsingEncoding:NSUTF8StringEncoding];
    if (_csvBytes + data.length > 5*1024*1024) return;
    @try { [_csv writeData:data]; _csvBytes+=data.length; } @catch(NSException* e) { [_csv closeFile];_csv=nil; [NSUserDefaults.standardUserDefaults setBool:NO forKey:Key(@"csv")]; }
}
- (void)exportCSV {
    NSURL* path=[_documents URLByAppendingPathComponent:@"performance.csv"];
    if(![NSFileManager.defaultManager fileExistsAtPath:path.path])return;
    UIViewController* host=_controller.presentedViewController?:_controller;
    UIActivityViewController* share=[[UIActivityViewController alloc] initWithActivityItems:@[path] applicationActivities:nil];
    share.popoverPresentationController.sourceView=host.view; share.popoverPresentationController.sourceRect=CGRectMake(host.view.bounds.size.width/2,40,1,1);
    [host presentViewController:share animated:YES completion:nil];
}
@end
@implementation PerformanceSettings
- (void)close { [self dismissViewControllerAnimated:YES completion:nil]; }
- (NSInteger)numberOfSectionsInTableView:(UITableView*)table { return 5; }
- (NSInteger)tableView:(UITableView*)table numberOfRowsInSection:(NSInteger)section { return section==0?(NSInteger)Keys().count+1:section==1?8:section==2?10:1; }
- (NSString*)tableView:(UITableView*)table titleForHeaderInSection:(NSInteger)section { return @[@"Performance Indicators",@"Appearance and Recording",@"Geometry Experiments",@"Renderer Experiment",@"Measurement File"][section]; }
- (NSString*)tableView:(UITableView*)table titleForFooterInSection:(NSInteger)section {
    if(section==0)return @"Samples cover the last 2 seconds. FPS counts presented frames and cannot distinguish repeated images. CPU 100% means one fully used core. GPU time covers only the display command buffer. Render time includes waits. Memory headroom estimates remaining allocation capacity for this app, not free device RAM.";
    if(section==1)return @"This panel does not pause the game. Preferences are saved. Metal lighting and SSAO changes take effect after restarting the app. Metal SSAO requires Metal lighting. Peak memory is the highest once-per-second sample. CSV recording is limited to 5 MiB.";
    if(section==2)return @"Preset order is Skinning / Culling. Select both routes with one tap or use the individual switches. The original SPU route is the default; all new routes are experimental. ARM64 and Metal cannot both be enabled for the same task. Changes apply on the next call. Metal prepares in the background on first selection; original code runs until ready. Keep validation enabled when testing a route for the first time: every call is compared with the original code, so this is not an FPS test. With validation disabled, the first 8 calls are still checked. A mismatch blocks the affected route until the app restarts. Metal selection uses a CPU/GPU hybrid: small or dependent tasks, and tasks measured as slower on the GPU, stay on the CPU. Culling output packing runs sequentially on the CPU. The HUD GPU batch count shows actual GPU coverage; zero means no GPU acceleration was measured.";
    if(section==3)return @"Skips unused legacy 3D state updates only on the active Metal dispatch path. Label, reference and draw notifications still use the original processor. Restart the app to apply changes. Diagnostics or the legacy backend retain the full path. An FPS gain has not yet been established on the device.";
    return @"Enable Record measurements to file first. Share the CSV here or retrieve it using the Files app.";
}
- (UITableViewCell*)tableView:(UITableView*)table cellForRowAtIndexPath:(NSIndexPath*)index {
    UITableViewCell* cell=[[UITableViewCell alloc] initWithStyle:index.section==2&&index.row>=5?UITableViewCellStyleSubtitle:UITableViewCellStyleDefault reuseIdentifier:nil];
    if(index.section==2&&index.row>=5){
        unsigned preset=(unsigned)index.row-5,skin=GeometryPresets[preset][0],cull=GeometryPresets[preset][1];
        cell.textLabel.text=GeometryPair(skin,cull);cell.detailTextLabel.text=@"Skinning / Culling · preset";
        cell.accessibilityIdentifier=[NSString stringWithFormat:@"performance.geometry-preset-%u-%u",skin,cull];
        NSUserDefaults*d=NSUserDefaults.standardUserDefaults;
        cell.accessoryType=GeometryChoice(d,0)==skin&&GeometryChoice(d,1)==cull?UITableViewCellAccessoryCheckmark:UITableViewCellAccessoryNone;
        return cell;
    }
    if(index.section==4) { cell.textLabel.text=@"Share CSV File"; cell.accessoryType=UITableViewCellAccessoryDisclosureIndicator;return cell; }
    NSString* name; NSString* title;
    if(index.section==0) {name=index.row==0?@"visible":Keys()[index.row-1];title=index.row==0?@"Show Indicators":Titles()[index.row-1];}
    else if(index.section==3){name=@"rsx-legacy-fast";title=@"Reduce redundant RSX state processing";}
    else if(index.section==2){name=@[@"skin-arm64",@"skin-metal",@"cull-arm64",@"cull-metal",@"geometry-validation"][index.row];title=@[@"ARM64 skinning · experimental",@"Metal + CPU skinning · experimental",@"ARM64 culling · experimental",@"Metal + CPU culling · experimental",@"Validate every call against original code"][index.row];}
    else {name=@[@"right",@"large",@"awake",@"csv",@"metal-lighting",@"metal-ssao",@"verified-fast-paths",@"dma-poison-skip"][index.row];title=@[@"Indicators on the right",@"Large text",@"Keep screen awake",@"Record measurements to file",@"Metal lighting · experimental",@"Metal SSAO · experimental",@"Combined optimizations · restart required",@"Skip DMA poison scan · experimental, restart"][index.row];}
    cell.textLabel.text=title; UISwitch* toggle=[UISwitch new];toggle.accessibilityIdentifier=Key(name);toggle.on=[NSUserDefaults.standardUserDefaults boolForKey:Key(name)];
    __weak PerformanceSettings* weakSelf=self;
    [toggle addAction:[UIAction actionWithHandler:^(UIAction* action){ BOOL on=((UISwitch*)action.sender).on;NSUserDefaults*d=NSUserDefaults.standardUserDefaults;[d setBool:on forKey:Key(name)];
        if(on&&index.section==2&&index.row<4){NSString*other=@[@"skin-metal",@"skin-arm64",@"cull-metal",@"cull-arm64"][index.row];[d setBool:NO forKey:Key(other)];}
        [weakSelf.owner changed];if(index.section==2)[weakSelf.tableView reloadSections:[NSIndexSet indexSetWithIndex:2] withRowAnimation:UITableViewRowAnimationNone]; }] forControlEvents:UIControlEventValueChanged];
    cell.accessoryView=toggle;cell.selectionStyle=UITableViewCellSelectionStyleNone;return cell;
}
- (void)tableView:(UITableView*)table didSelectRowAtIndexPath:(NSIndexPath*)index {
    [table deselectRowAtIndexPath:index animated:YES];
    if(index.section==4){[self.owner exportCSV];return;}
    if(index.section==2&&index.row>=5){
        unsigned preset=(unsigned)index.row-5;if(preset>=5)return;NSUserDefaults*d=NSUserDefaults.standardUserDefaults;
        for(unsigned kind=0;kind<2;kind++){
            NSString*prefix=kind?@"cull":@"skin";unsigned route=GeometryPresets[preset][kind];
            [d setBool:route==1 forKey:Key([prefix stringByAppendingString:@"-arm64"])];
            [d setBool:route==2 forKey:Key([prefix stringByAppendingString:@"-metal"])];
        }
        [self.owner changed];[table reloadSections:[NSIndexSet indexSetWithIndex:2] withRowAnimation:UITableViewRowAnimationNone];
    }
}
@end
