import org.matsim.api.core.v01.network.Link;
import org.matsim.api.core.v01.network.Network;
import org.matsim.core.network.NetworkUtils;
import org.matsim.core.network.io.MatsimNetworkReader;
import org.matsim.core.network.io.NetworkChangeEventsWriter;
import org.matsim.core.network.NetworkChangeEvent;
import org.matsim.core.network.NetworkChangeEvent.ChangeValue;
import org.matsim.core.network.NetworkChangeEvent.ChangeType;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/**
 * Goal: Generate a single network change events XML file containing both
 * dynamic (time-based) and static (permanent from t=0) interventions
 * for the 'Altstadt fur alle' policy scenario using OSM street names.
 */
public class AltstadtEventsGenerator {

    public static void main(String[] args) {
        System.out.println("Initiating Altstadt Network Events Generation...");

        String inputNetwork = "D:/Michael_Thesis/data/eqasim_population_bavaria/munich_1pct_network_connected.xml.gz";
        String outputDir = "D:/Michael_Thesis/data/eqasim_population_bavaria/interventions/";
        new File(outputDir).mkdirs();

        String outputEvents = outputDir + "altstadt_change_events_speed_0.xml.gz";

        Network network = NetworkUtils.createNetwork();
        new MatsimNetworkReader(network).readFile(inputNetwork);

        List<NetworkChangeEvent> networkChangeEvents = new ArrayList<>();

        // Intervention Parameters
        double schoolStartTime = 7 * 3600.0;
        double schoolEndTime = 14 * 3600.0;
        double targetSpeedApproach = 10.0 / 3.6; // 10 km/h
        double targetSpeedMax = 20.0 / 3.6; // 20 km/h
        double baseCapacityPerLane = 600.0; // Standardize to 600 veh/hr per physical lane

        // Counters for validation
        int herzogspitalCount = 0;
        int approachCount = 0;
        int maximilianCount = 0;

        System.out.println("Scanning network links for target streets...");

        // Loop through all links in the network
        for (Link link : network.getLinks().values()) {

            // Fetch the osm:way:name attribute
            Object nameAttribute = link.getAttributes().getAttribute("osm:way:name");

            if (nameAttribute != null) {
                String streetName = nameAttribute.toString();

                // ==========================================
                // 1. DYNAMIC INTERVENTION: Herzogspitalstraße
                // ==========================================
                if (streetName.equals("Herzogspitalstraße")) {
                    double originalFreespeed = link.getFreespeed();

                    // Event 1: Close street
                    NetworkChangeEvent closeEvent = new NetworkChangeEvent(schoolStartTime);
                    closeEvent.addLink(link);
                    closeEvent.setFreespeedChange(new ChangeValue(ChangeType.ABSOLUTE_IN_SI_UNITS, 0.0));
                    networkChangeEvents.add(closeEvent);

                    // Event 2: Reopen street
                    NetworkChangeEvent openEvent = new NetworkChangeEvent(schoolEndTime);
                    openEvent.addLink(link);
                    openEvent.setFreespeedChange(new ChangeValue(ChangeType.ABSOLUTE_IN_SI_UNITS, originalFreespeed));
                    networkChangeEvents.add(openEvent);

                    herzogspitalCount++;
                }

                // ==========================================
                // 2. PERMANENT INTERVENTION: Stollbergstraße & Hildegardstraße
                // ==========================================
                else if (streetName.equals("Stollbergstraße") || streetName.equals("Hildegardstraße")) {
                    NetworkChangeEvent speedReductionEvent = new NetworkChangeEvent(0.0);
                    speedReductionEvent.addLink(link);
                    speedReductionEvent.setFreespeedChange(new ChangeValue(ChangeType.ABSOLUTE_IN_SI_UNITS, targetSpeedApproach));
                    networkChangeEvents.add(speedReductionEvent);

                    approachCount++;
                }

                // ==========================================
                // 3. PERMANENT INTERVENTION: Maximilianstraße
                // ==========================================
                else if (streetName.equals("Maximilianstraße")) {
                    double currentLanes = link.getNumberOfLanes();
                    double newLanes = currentLanes;

                    // Reduce lanes by 1 if there are multiple lanes (minimum 1 lane remains)
                    if (currentLanes > 1.0) {
                        newLanes = currentLanes - 1.0;
                    }

                    // Standardize capacity based on the new physical lanes
                    double newCapacity = newLanes * baseCapacityPerLane;

                    NetworkChangeEvent capacitySpeedEvent = new NetworkChangeEvent(0.0);
                    capacitySpeedEvent.addLink(link);
                    capacitySpeedEvent.setFreespeedChange(new ChangeValue(ChangeType.ABSOLUTE_IN_SI_UNITS, targetSpeedMax));
                    capacitySpeedEvent.setFlowCapacityChange(new ChangeValue(ChangeType.ABSOLUTE_IN_SI_UNITS, newCapacity));
                    capacitySpeedEvent.setLanesChange(new ChangeValue(ChangeType.ABSOLUTE_IN_SI_UNITS, newLanes));
                    networkChangeEvents.add(capacitySpeedEvent);

                    maximilianCount++;
                }
            }
        }

        // ==========================================
        // EXPORT & VALIDATION LOGS
        // ==========================================
        System.out.println("--- Link Modification Summary ---");
        System.out.println("Herzogspitalstrasse links modified: " + herzogspitalCount);
        System.out.println("Approach streets links modified: " + approachCount);
        System.out.println("Maximilianstrasse links modified: " + maximilianCount);
        System.out.println("---------------------------------");

        NetworkChangeEventsWriter eventsWriter = new NetworkChangeEventsWriter();
        eventsWriter.write(outputEvents, networkChangeEvents);
        System.out.println("Network change events successfully written to: " + outputEvents);
    }
}