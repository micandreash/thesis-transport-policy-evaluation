import org.matsim.api.core.v01.Scenario;
import org.matsim.api.core.v01.network.Link;
import org.matsim.contrib.accidents.AccidentsConfigGroup;
import org.matsim.contrib.accidents.AccidentsModule;
import org.matsim.core.config.Config;
import org.matsim.core.config.ConfigUtils;
import org.matsim.core.controler.AbstractModule;
import org.matsim.core.controler.Controler;
import org.matsim.core.controler.OutputDirectoryHierarchy;
import org.matsim.core.events.MatsimEventsReader;
import org.matsim.core.mobsim.framework.Mobsim;
import org.matsim.core.scenario.ScenarioUtils;

import java.io.File;

public class OfflineAccidentsCalculator {

    public static void main(String[] args) {
        System.out.println("Initiating Offline Accidents Calculator...");

        // ==========================================
        // 1. SETUP DIRECTORIES AND FILE PATHS
        // ==========================================
        String baseDir = "D:/Michael_Thesis/data/final_indicators/";
        String outputDir = baseDir + "accidents_altstadt/";
        new File(outputDir).mkdirs();

        String networkFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_munich_1pct_network_connected.xml.gz";
        String eventsFile = "D:/Michael_Thesis/data/eqasim_population_bavaria/final_simulation_output_altstadt/ITERS/it.116/116.events.xml.gz";

        // ==========================================
        // 2. CONFIGURE ACCIDENTS PARAMETERS
        // ==========================================
        AccidentsConfigGroup accidentsConfig = new AccidentsConfigGroup();
        accidentsConfig.setEnableAccidentsModule(true);
        accidentsConfig.setScaleFactor(100.0);
        accidentsConfig.AccidentsComputationMethod(AccidentsConfigGroup.AccidentsComputationMethod.BVWP);

        // ==========================================
        // 3. CONFIGURE MATSIM CORE SCENARIO
        // ==========================================
        Config config = ConfigUtils.createConfig(accidentsConfig);

        // Input setups
        config.network().setInputFile(networkFile);

        // Output and controler setups
        config.controler().setOutputDirectory(outputDir);
        config.controler().setLastIteration(0);
        config.controler().setOverwriteFileSetting(OutputDirectoryHierarchy.OverwriteFileSetting.deleteDirectoryIfExists);

        // Global setups
        config.global().setCoordinateSystem("EPSG:25832");
        config.global().setNumberOfThreads(64);

        System.out.println("Loading MATSim scenario with Network...");
        Scenario scenario = ScenarioUtils.loadScenario(config);

        // ==========================================
        // 4. INJECT NETWORK ATTRIBUTES FOR ACCIDENTS
        // ==========================================
        System.out.println("Injecting mandatory accident computation attributes to network links...");
        for (Link link : scenario.getNetwork().getLinks().values()) {
            link.getAttributes().putAttribute("accidentsComputationMethod", "BVWP");

            String osmHighway = (String) link.getAttributes().getAttribute("osm:way:highway");
            double speedKmh = link.getFreespeed() * 3.6;

            int index0 = 1;
            int index1 = 3;
            int index2 = (int) link.getNumberOfLanes();

            if (index2 < 1) index2 = 1;
            if (index2 > 4) index2 = 4;

            boolean isBuiltUp = true;

            if (osmHighway != null) {
                if (osmHighway.contains("motorway")) {
                    index0 = 0;
                    isBuiltUp = speedKmh <= 90;
                } else if (osmHighway.contains("trunk") || osmHighway.contains("primary") ||
                        osmHighway.contains("secondary") || osmHighway.contains("tertiary") ||
                        osmHighway.contains("unclassified")) {
                    index0 = 1;
                    isBuiltUp = speedKmh <= 50;
                } else if (osmHighway.contains("residential") || osmHighway.contains("living_street")) {
                    index0 = 1;
                    isBuiltUp = true;
                }
            } else {
                if (speedKmh > 90) {
                    index0 = 0;
                    isBuiltUp = false;
                } else {
                    index0 = 1;
                    isBuiltUp = speedKmh <= 50;
                }
            }

            if (isBuiltUp) {
                index1 = (speedKmh > 57.6) ? 1 : 3;
            } else {
                index1 = (speedKmh > 57.6) ? 0 : 2;
            }

            String bvwpType = index0 + "," + index1 + "," + index2;
            link.getAttributes().putAttribute("bvwpRoadType", bvwpType);
        }

        // ==========================================
        // 5. EXECUTE ACCIDENTS COMPUTATION (EVENT PLAYBACK)
        // ==========================================
        System.out.println("Starting 0-iteration calculation with injected events state...");
        Controler controler = new Controler(scenario);

        controler.addOverridingModule(new AccidentsModule());
        controler.addOverridingModule(new AbstractModule() {
            @Override
            public void install() {
                bindMobsim().toProvider(new com.google.inject.Provider<Mobsim>() {
                    @Override
                    public Mobsim get() {
                        return new Mobsim() {
                            @Override
                            public void run() {
                                System.out.println("Playing back events from: " + eventsFile);
                                new MatsimEventsReader(controler.getEvents()).readFile(eventsFile);
                            }
                        };
                    }
                });
            }
        });

        controler.run();
        System.out.println("Offline standard accidents calculation completed. Results generated in: " + outputDir);
    }
}