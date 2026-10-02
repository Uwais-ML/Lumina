package lumina;
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
                 pythonselect = "/windows/python.exe"; 
            }
            else if (osName.contains("mac") && arch.contains("x86")){
                 pythonselect = "/macos-intel/bin/python3";
            }
            else if (osName.contains("lin")){
                 pythonselect = "/linux-intel/bin/python3"; 
            }
            String projectRoot = System.getProperty("user.dir");
            String baseDir = projectRoot + "/python-dependencies";
            String scriptPath = projectRoot + "/scripts/download_model.py";
            String pythonExe = baseDir + pythonselect;
            if (!new File(pythonExe).exists()) {
                pythonExe = "python3";
            }
            ProcessBuilder pb = new ProcessBuilder(
                pythonExe,
                scriptPath,
                repoId,
                filename,
                "models/"
            );

            // Inject PYTHONPATH if site-packages exists
            String pathSep = osName.contains("win") ? ";" : ":";
            String spWin = baseDir + "/windows/Lib/site-packages";
            String spMac = baseDir + "/macos-intel/lib/python3.12/site-packages";
            String spTarget = new File(spWin).exists() ? spWin : (new File(spMac).exists() ? spMac : null);
            if (spTarget != null) {
                String existing = pb.environment().get("PYTHONPATH");
                pb.environment().put("PYTHONPATH", spTarget + (existing != null ? pathSep + existing : ""));
            }
            
            pb.directory(new File(projectRoot));
            Runtime.getRuntime().addShutdownHook(new Thread(downloadmodel::shutdownhook));
            pb.inheritIO(); 
            process = pb.start();

            int exitCode = process.waitFor();
            System.out.println("Download process exited with code: " + exitCode);
        }
        return process;
    }

    public static void main(String[] args) {
        if (args.length == 0) {
            System.out.println("Please provide a model ID to download. Example: lumina --download 1");
            return;
        }
        try {
            int modelId = Integer.parseInt(args[0]);
            downloadmodel(modelId);
        } catch (NumberFormatException e) {
            System.err.println("Invalid model ID: " + args[0] + ". Please provide an integer ID.");
        } catch (Exception e) {
            System.err.println("Error downloading model: " + e.getMessage());
        }
    }

}


