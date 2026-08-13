package com.example;
import java.util.List;
import java.io.File;

public class downloadmodel {
    static Process process;

    public static void shutdownhook(){
        if (process != null && process.isAlive()){
            System.out.println("Process is still running. Terminating the process...");
            process.destroyForcibly();
        }
    }

    public static Process downloadmodel(int id) throws Exception {
        List<String> llminfo = LLM.llmsearch(id);
        if (llminfo != null){
            String link = llminfo.get(0);
            String filename = llminfo.get(1);
            System.out.println("Downloading model from link: " + link);
            System.out.println("Filename pattern: " + filename);
            String cleanLink = link.replace("https://huggingface.co", "");
            String[] parts = cleanLink.split("/resolve/main/");
            String repoId = parts[0];


            if (repoId.startsWith("/")) {
                repoId = repoId.substring(1);
            }
            System.out.println("Repo ID: " + repoId);
            
            String osName = System.getProperty("os.name").toLowerCase();
            String arch = System.getProperty("os.arch").toLowerCase();
            String pythonselect = "";

            if (osName.contains("win")){
                 pythonselect = "/windows-intel/python.exe"; 
            }
            else if (osName.contains("mac") && arch.contains("x86")){
                 pythonselect = "/macos-intel/bin/python3";
            }
            else if (osName.contains("lin")){
                 pythonselect = "/linux-intel/bin/python3"; 
            }
            String projectRoot = System.getProperty("user.dir");
            String baseDir = projectRoot + "/python-dependencies";
            String scriptPath = projectRoot + "/PythonFile/DownloadModel.py";
            ProcessBuilder pb = new ProcessBuilder(
                baseDir + pythonselect,
                scriptPath,
                repoId,
                filename,
                "src/main/java/com/example/LLMs/"
            );
            
            pb.directory(new File(projectRoot));
            Runtime.getRuntime().addShutdownHook(new Thread(downloadmodel::shutdownhook));
            pb.inheritIO(); 
            process = pb.start();

            int exitCode = process.waitFor();
            System.out.println("Download process exited with code: " + exitCode);
        }
        return process;
    }

}


