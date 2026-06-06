diff --git a/node_modules/react-native/ReactCommon/react/nativemodule/core/platform/ios/ReactCommon/RCTTurboModule.mm b/node_modules/react-native/ReactCommon/react/nativemodule/core/platform/ios/ReactCommon/RCTTurboModule.mm
index 0000000..0000000 100644
--- a/node_modules/react-native/ReactCommon/react/nativemodule/core/platform/ios/ReactCommon/RCTTurboModule.mm
+++ b/node_modules/react-native/ReactCommon/react/nativemodule/core/platform/ios/ReactCommon/RCTTurboModule.mm
@@ -432,14 +432,16 @@ void ObjCTurboModule::performVoidMethodInvocation(
       TurboModulePerfLogger::asyncMethodCallExecutionStart(moduleName, methodName, asyncCallCounter);
     }
 
     @try {
       [inv invokeWithTarget:strongModule];
     } @catch (NSException *exception) {
-      throw convertNSExceptionToJSError(runtime, exception, std::string{moduleName}, methodNameStr);
+      // Void methods are always async, re-throw instead of converting to
+      // JSError, same as the async branch in performMethodInvocation.
+      @throw exception;
     } @finally {
       [retainedObjectsForInvocation removeAllObjects];
     }
 
     if (shouldVoidMethodsExecuteSync_) {
       TurboModulePerfLogger::syncMethodCallExecutionEnd(moduleName, methodName);
     } else {
