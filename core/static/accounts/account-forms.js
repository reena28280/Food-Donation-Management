document.addEventListener('DOMContentLoaded', () => {
    const roleField = document.getElementById('id_role');
    const organizationField = document.getElementById('id_organization_type');
    if (!roleField || !organizationField) return;

    const choicesByRole = {
        DONOR: [
            ['COLLEGE', 'College'],
            ['HOSTEL', 'Hostel'],
            ['RESTAURANT', 'Restaurant'],
            ['HOTEL', 'Hotel'],
            ['EVENT', 'Event Organizer'],
            ['INDIVIDUAL', 'Individual'],
        ],
        RECEIVER: [
            ['NGO', 'NGO'],
            ['COMMUNITY', 'Community Kitchen'],
            ['CHARITY', 'Charitable Organization'],
            ['COMMUNITY_GROUP', 'Community Group'],
            ['ORPHANAGE', 'Orphanage'],
            ['OLD_AGE_HOME', 'Old-age home'],
            ['COMMUNITY_CENTRE', 'Community centre'],
        ],
        VOLUNTEER: [
            ['COLLEGE', 'College'],
            ['HOSTEL', 'Hostel'],
            ['NGO', 'NGO'],
            ['COMMUNITY', 'Community Kitchen'],
            ['INDIVIDUAL', 'Individual'],
            ['OTHER', 'Other'],
        ],
    };

    const updateOrganizations = () => {
        const previousValue = organizationField.value;
        const choices = choicesByRole[roleField.value] || [];
        organizationField.replaceChildren(new Option('Select organization type', ''));
        choices.forEach(([value, label]) => organizationField.add(new Option(label, value)));
        if (choices.some(([value]) => value === previousValue)) {
            organizationField.value = previousValue;
        } else if (choices.length === 1) {
            organizationField.value = choices[0][0];
        }
    };

    roleField.addEventListener('change', updateOrganizations);
    updateOrganizations();
});