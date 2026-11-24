#import <Foundation/Foundation.h>

// A pthread has no UIKit run loop to drain temporary Objective-C objects.
// Bound their lifetime to each renderer batch, idle flush, or teardown.
void apple_runtime_with_pool(void (*work)(void*), void* context) {
    @autoreleasepool { work(context); }
}
