package com.faweisi.kanban;

import android.content.ContentResolver;
import android.net.Uri;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

final class AttachmentSaver {
    record Download(String url, String cookie, String userAgent) { }

    static void save(ContentResolver resolver, Uri destination, Download download, OriginPolicy policy) throws IOException {
        if (!policy.isAttachment(download.url())) throw new IOException("Untrusted download");
        HttpURLConnection connection = (HttpURLConnection) new URL(download.url()).openConnection();
        try {
            // Never forward the session cookie to a redirect destination.
            connection.setInstanceFollowRedirects(false);
            connection.setConnectTimeout(15000);
            connection.setReadTimeout(30000);
            connection.setRequestProperty("User-Agent", download.userAgent());
            if (download.cookie() != null) connection.setRequestProperty("Cookie", download.cookie());
            if (connection.getResponseCode() != 200) throw new IOException("Attachment unavailable");
            try (InputStream input = connection.getInputStream();
                 OutputStream output = resolver.openOutputStream(destination, "wt")) {
                if (output == null) throw new IOException("Cannot open destination");
                byte[] buffer = new byte[16384];
                int count;
                while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            }
        } finally {
            connection.disconnect();
        }
    }
}
