package com.example;

import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpExchange;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.fasterxml.jackson.databind.node.ArrayNode;

import java.io.*;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import java.util.concurrent.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class LuminaWebServer {
    private static final int DEFAULT_PORT = 8080;
    private static final ObjectMapper mapper = new ObjectMapper();
    private static final SystemAssess sysAssess = new SystemAssess();
    private static volatile boolean isDownloading = false;
    private static volatile Integer currentDownloadingId = null;
    private static volatile Integer lastExitCode = null;
    private static final List<String> logLines = Collections.synchronizedList(new ArrayList<>());
    private static final ExecutorService executor = Executors.newSingleThreadExecutor();

    public static void main(String[] args) throws Exception {
        int port = DEFAULT_PORT;
        HttpServer server = null;

        while (port < 8999) {
            try {
                server = HttpServer.create(new InetSocketAddress(port), 0);
                break;
            } catch (IOException e) {
                System.out.println("Failed to bind port " + port + ": " + e);
                port++;
            }
        }

        if (server == null) {
            System.err.println("Could not bind to any port in range 8080-8090.");
            return;
        }

        System.out.println("=================================================");
        System.out.println("✨ Lumina Web Server running locally!");
        System.out.println("👉 Access Web Dashboard at: http://localhost:" + port);
        System.out.println("=================================================");
        setupLogStream();

        server.createContext("/", new StaticHandler());
        server.createContext("/api/models", new ModelsHandler());
        server.createContext("/api/system", new SystemHandler());
        server.createContext("/api/install", new InstallHandler());
        server.createContext("/api/status", new StatusHandler());

        server.setExecutor(Executors.newFixedThreadPool(10));
        server.start();
    }

    private static void setupLogStream() {
        PrintStream originalOut = System.out;
        PrintStream customOut = new PrintStream(new OutputStream() {
            private final ByteArrayOutputStream buffer = new ByteArrayOutputStream();

            @Override
            public synchronized void write(int b) {
                originalOut.write(b);
                originalOut.flush();
                if (b == '\n') {
                    String line = buffer.toString(StandardCharsets.UTF_8).trim();
                    buffer.reset();
                    if (!line.isEmpty()) {
                        logLines.add(line);
                    }
                } else {
                    buffer.write(b);
                }
            }

            @Override
            public synchronized void write(byte[] b, int off, int len) {
                originalOut.write(b, off, len);
                originalOut.flush();
                String s = new String(b, off, len, StandardCharsets.UTF_8);
                for (String line : s.split("\\r?\\n")) {
                    if (!line.trim().isEmpty()) {
                        logLines.add(line.trim());
                    }
                }
            }
        }, true, StandardCharsets.UTF_8);

        System.setOut(customOut);
    }

    
    static class StaticHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            String path = exchange.getRequestURI().getPath();
            if (path.equals("/") || path.equals("/index.html")) {
                byte[] htmlBytes = loadWebAsset("web/index.html");
                if (htmlBytes != null) {
                    exchange.getResponseHeaders().set("Content-Type", "text/html; charset=UTF-8");
                    exchange.sendResponseHeaders(200, htmlBytes.length);
                    try (OutputStream os = exchange.getResponseBody()) {
                        os.write(htmlBytes);
                    }
                    return;
                }
            }
            sendTextResponse(exchange, 404, "Page Not Found");
        }
    }

    private static byte[] loadWebAsset(String resourcePath) throws IOException {
        InputStream is = LuminaWebServer.class.getClassLoader().getResourceAsStream(resourcePath);
        if (is != null) {
            return is.readAllBytes();
        }
        File file = new File("src/main/resources/" + resourcePath);
        if (file.exists()) {
            return Files.readAllBytes(file.toPath());
        }
        return null;
    }

    static class SystemHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendTextResponse(exchange, 405, "Method Not Allowed");
                return;
            }

            ObjectNode res = mapper.createObjectNode();
            double bw = 37.32; 
            try {
                File bwFile = new File("src/main/java/com/example/resources/bandwidth.txt");
                if (bwFile.exists()) {
                    String content = Files.readString(bwFile.toPath()).trim();
                    bw = Double.parseDouble(content);
                }
            } catch (Exception ignored) {}

            res.put("bandwidth", bw);
            res.put("os", System.getProperty("os.name"));
            res.put("arch", System.getProperty("os.arch"));

            sendJsonResponse(exchange, 200, res.toString());
        }
    }

    static class ModelsHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendTextResponse(exchange, 405, "Method Not Allowed");
                return;
            }

            try {
                File jsonFile = new File("src/main/java/com/example/resources/jsonfiles/llmstore.json");
                JsonNode rootNode = mapper.readTree(jsonFile);
                ArrayNode resultList = mapper.createArrayNode();

                if (rootNode.isArray()) {
                    for (JsonNode node : rootNode) {
                        ObjectNode modelObj = node.deepCopy();

                        String paramStr = node.path("parameters").asText("");
                        String quantStr = node.path("quantization").asText("");

                        double paramNum = parseParameters(paramStr);
                        double quantNum = parseQuantization(quantStr);

                        double sizeGb = paramNum * (quantNum / 8.0);
                        double estimatedTs = sysAssess.estimate(paramNum, quantNum);
                        boolean fits = sysAssess.willitfit(paramNum, (int) Math.round(quantNum));

                        modelObj.put("parsed_param_b", paramNum);
                        modelObj.put("parsed_quant_bits", quantNum);
                        modelObj.put("estimated_size_gb", sizeGb);
                        modelObj.put("estimated_ts", estimatedTs);
                        modelObj.put("fits_hardware", fits);

                        resultList.add(modelObj);
                    }
                }

                sendJsonResponse(exchange, 200, resultList.toString());
            } catch (Exception e) {
                e.printStackTrace();
                sendTextResponse(exchange, 500, "Error reading llmstore.json: " + e.getMessage());
            }
        }
    }

   
    static class InstallHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendTextResponse(exchange, 405, "Method Not Allowed");
                return;
            }

            if (isDownloading) {
                ObjectNode err = mapper.createObjectNode();
                err.put("error", "An installation process is already running for model ID " + currentDownloadingId);
                sendJsonResponse(exchange, 400, err.toString());
                return;
            }

            String body = new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8);
            int modelId = -1;
            try {
                JsonNode json = mapper.readTree(body);
                if (json.has("id")) {
                    modelId = json.get("id").asInt();
                }
            } catch (Exception e) {
                sendTextResponse(exchange, 400, "Invalid JSON input");
                return;
            }

            if (modelId <= 0) {
                sendTextResponse(exchange, 400, "Invalid Model ID");
                return;
            }

            final int idToRun = modelId;
            isDownloading = true;
            currentDownloadingId = idToRun;
            lastExitCode = null;
            logLines.clear();

            logLines.add("[Lumina] Initiating download task for Model ID: " + idToRun);

            executor.submit(() -> {
                try {
                   Process process = downloadmodel.downloadmodel(idToRun);
                   process.waitFor();
                    lastExitCode = 0;
                    logLines.add("[Lumina] Model download completed successfully!");
                } catch (Exception e) {
                    lastExitCode = 1;
                    logLines.add("[Lumina ❌] Exception during download: " + e.getMessage());
                    e.printStackTrace();
                } finally {
                    isDownloading = false;
                }
            });

            ObjectNode res = mapper.createObjectNode();
            res.put("status", "started");
            res.put("id", modelId);
            sendJsonResponse(exchange, 200, res.toString());
        }
    }

    static class StatusHandler implements HttpHandler {
        @Override
        public void handle(HttpExchange exchange) throws IOException {
            if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
                sendTextResponse(exchange, 405, "Method Not Allowed");
                return;
            }

            ObjectNode res = mapper.createObjectNode();
            res.put("isDownloading", isDownloading);
            if (currentDownloadingId != null) {
                res.put("currentModelId", currentDownloadingId);
            } else {
                res.putNull("currentModelId");
            }
            if (lastExitCode != null) {
                res.put("lastExitCode", lastExitCode);
            } else {
                res.putNull("lastExitCode");
            }

            ArrayNode logsArray = mapper.createArrayNode();
            synchronized (logLines) {
                for (String line : logLines) {
                    logsArray.add(line);
                }
            }
            res.set("logs", logsArray);

            sendJsonResponse(exchange, 200, res.toString());
        }
    }

    private static double parseParameters(String paramStr) {
        if (paramStr == null || paramStr.isEmpty()) return 7.0;
        String clean = paramStr.toUpperCase().trim();

        if (clean.contains("X")) {
            String[] parts = clean.split("X");
            try {
                double mult = Double.parseDouble(parts[0].replaceAll("[^0-9.]", ""));
                double base = Double.parseDouble(parts[1].replaceAll("[^0-9.]", ""));
                return mult * base;
            } catch (Exception ignored) {}
        }

        Pattern p = Pattern.compile("([0-9.]+)\\s*B?");
        Matcher m = p.matcher(clean);
        if (m.find()) {
            try {
                return Double.parseDouble(m.group(1));
            } catch (Exception ignored) {}
        }
        return 7.0;
    }

    private static double parseQuantization(String quantStr) {
        if (quantStr == null) return 4.83;
        String upper = quantStr.toUpperCase();
        if (upper.contains("Q8_0") || upper.contains("Q8")) return 8.0;
        if (upper.contains("Q4_K_M") || upper.contains("Q4_K") || upper.contains("Q4")) return 4.83;

        Pattern p = Pattern.compile("Q(\\d+)");
        Matcher m = p.matcher(upper);
        if (m.find()) {
            try {
                return Double.parseDouble(m.group(1));
            } catch (Exception ignored) {}
        }
        return 4.83;
    }

    private static void sendJsonResponse(HttpExchange exchange, int statusCode, String jsonResponse) throws IOException {
        byte[] bytes = jsonResponse.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=UTF-8");
        exchange.sendResponseHeaders(statusCode, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static void sendTextResponse(HttpExchange exchange, int statusCode, String textResponse) throws IOException {
        byte[] bytes = textResponse.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/plain; charset=UTF-8");
        exchange.sendResponseHeaders(statusCode, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }
}
