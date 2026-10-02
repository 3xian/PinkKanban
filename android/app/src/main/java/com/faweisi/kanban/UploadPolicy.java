package com.faweisi.kanban;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ProviderInfo;
import android.net.Uri;
import android.os.Process;

/** Only explicitly granted content from another app may be sent to the webpage. */
final class UploadPolicy {
    static boolean isAllowed(Context context, Uri[] files) {
        if (files.length == 0) return false;
        for (Uri uri : files) {
            if (uri == null || !"content".equals(uri.getScheme()) || uri.getAuthority() == null) return false;
            ProviderInfo provider = context.getPackageManager().resolveContentProvider(uri.getAuthority(), 0);
            if (provider == null || provider.applicationInfo.uid == Process.myUid()) return false;
            if (context.checkUriPermission(uri, Process.myPid(), Process.myUid(),
                    Intent.FLAG_GRANT_READ_URI_PERMISSION) != PackageManager.PERMISSION_GRANTED) return false;
        }
        return true;
    }
}
